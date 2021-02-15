# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
pythonic RPC implementation using simple rpc with msgpack.

Server example::

    from bliss.comm.rpc import Server

    class Car(object):
        '''A silly car. This doc should show up in the client'''

        wheels = 4

        def __init__(self, color, horsepower):
            self.horsepower = horsepower
            self.__position = 0

        @property
        def position(self):
            '''this doc should show up in the client too'''
            return self.__position

        @staticmethod
        def horsepower_to_watts(horsepower):
            '''so should this'''
             return horsepower * 735.499

        @property
        def watts(self):
            '''also this one'''
            return self.horsepower_to_watts(self.horsepower)

        def move(self, value, relative=False):
            '''needless to say this one as well'''
            if relative:
                 self.__position += value
            else:
                 self.__position = value

    car = Car('yellow', 120)
    server = Server(car)
    server.bind('tcp://0:8989')
    server.run()


Client::

    from bliss.comm.rpc import Client

    car = Client('tcp://localhost:8989')

    assert car.__doc__
    assert type(car).__name__ == 'Car'
    assert car.position == 0
    assert car.horsepower == 120.0
    assert car.horsepower_to_watts(1) == 735.499
    assert car.watts == 120 * 735.499
    car.move(12)
    assert car.position == 12
    car.move(10, relative=True)
    assert car.position == 22

"""
import psutil
import sys

import os
import re
import inspect
import logging
import weakref
import itertools
import contextlib
import numpy
import louie
import gevent.lock
from gevent import socket

from bliss.common.greenlet_utils import KillMask
from bliss.common.utils import StripIt
from bliss.common import proxy

from bliss.common.logtools import log_debug
from bliss import global_map

from bliss.common.msgpack_ext import MsgpackContext


MAX_MEMORY = min(psutil.virtual_memory().total, sys.maxsize)
MAX_BUFFER_SIZE = int(MAX_MEMORY * 0.8)
READ_BUFFER_SIZE = int(128 * 1024)


@contextlib.contextmanager
def switch_temporary_lowdelay(fd):
    """
    Switch temparary socket to low delay on tcp socket.
    So we disable Nagle
    algorithm and we set TOS (Type of service) to *low delay*.
    For unix socket operation is not supported so we go in except.
    """
    try:
        previous_no_delay = fd.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
        previous_tos = fd.getsockopt(socket.SOL_IP, socket.IP_TOS)
        fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        fd.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
    except OSError:
        yield socket
    else:
        try:
            yield socket
        finally:
            fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, previous_no_delay)
            fd.setsockopt(socket.SOL_IP, socket.IP_TOS, previous_tos)


msgpack = MsgpackContext()
# Registration order matter
msgpack.register_numpy()
msgpack.register_tb_exception()
msgpack.register_pickle()


SPECIAL_METHODS = set(
    (
        "abstractmethods",
        "new",
        "init",
        "del",
        "class",
        "dict",
        "sizeof",
        "weakref",
        "metaclass",
        "subclasshook",
        "getattr",
        "setattr",
        "delattr",
        "getattribute",
        "instancecheck",
        "subclasscheck",
        "reduce",
        "reduce_ex",
        "getstate",
        "setstate",
        "slots",
        "eq",
        "ne",
        "hash",
    )
)


class ServerError(Exception):
    pass


def _discover_object(obj):
    if isinstance(obj, proxy.Proxy):
        obj = obj.__wrapped__

    members = {}
    otype = type(obj)
    for name, member in inspect.getmembers(otype):
        info = dict(name=name, doc=inspect.getdoc(member))
        if callable(member):
            if inspect.ismethod(member) and member.__self__ == otype:
                member_type = "classmethod"
            elif inspect.isfunction(member):
                member_type = "staticmethod"
            else:
                member_type = "method"
        elif inspect.isdatadescriptor(member):
            member_type = "attribute"
        else:
            member_type = "attribute"
            info["doc"] = None
        info["type"] = member_type
        members[name] = info

    for name in dir(obj):
        if name.startswith("__") or name in members:
            continue
        member = getattr(obj, name)
        info = dict(name=name, doc=inspect.getdoc(member))
        if callable(member):
            member_type = "method"
        else:
            member_type = "attribute"
            info["doc"] = None
        info["type"] = member_type
        members[name] = info

    return dict(
        name=otype.__name__,
        module=inspect.getmodule(obj).__name__,
        doc=inspect.getdoc(obj),
        members=members,
    )


class _ServerObject(object):
    def __init__(self, obj, stream=False, tcp_low_latency=False):
        self._log = logging.getLogger(f"{__name__}.{type(obj).__name__}")
        self._object = obj
        self._metadata = _discover_object(obj)
        self._metadata["stream"] = stream
        self._stream = stream
        self._server_task = None
        self._clients = list()
        self._socket = None
        self._uds_name = None
        self._low_latency_signal = set()
        self._tcp_low_latency = tcp_low_latency

    def __dir__(self):
        result = ["_call__"]
        for name, info in self._metadata["members"].items():
            if "method" in info["type"]:
                result.append(name)
        return result

    def __getattr__(self, name):
        return getattr(self._object, name)

    def _get_object_class(self):
        obj = self._object
        if isinstance(obj, proxy.Proxy):
            return type(obj.__wrapped__)
        elif not inspect.ismodule(obj):
            # if obj is a module it cannot be pickled, and 'real_class' makes no sense
            return type(obj)

    def bind(self, url):
        if self._server_task is not None:
            self._server_task.kill()
        if url.startswith("tcp"):
            exp = re.compile("tcp://(.+?):([0-9]+)")
            m = exp.match(url)
            if not m:
                raise RuntimeError("Cannot manage this kind of url (%r)" % url)
            port = m.group(2)
            sock = socket.socket()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", int(port)))
        elif url.startswith("inproc") or url.startswith("ipc"):
            exp = re.compile("(inproc|ipc)://(.+)")
            m = exp.match(url)
            if not m:
                raise RuntimeError("Weird url %s" % url)
            uds_port_name = m.group(2)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                os.unlink(uds_port_name)
            except OSError:
                pass
            sock.bind(uds_port_name)
            self._uds_name = uds_port_name
        else:
            raise RuntimeError("don't manage this kind of url (%s)" % url)
        sock.listen(512)
        self._socket = sock

    def close(self):
        if self._socket:
            if self._uds_name:
                os.unlink(self._uds_name)
                self._uds_name = None
            self._socket.close()
            self._socket = None

    def run(self, ready_event=None):
        server_socket = self._socket
        if ready_event:
            ready_event.set()
        try:
            while True:
                new_client, addr = server_socket.accept()
                # On new client socket TOS is throughput due to stream event
                # this is changed when received a rpc call or
                # one low delay event.
                # except if all event are low delay.
                try:
                    if self._tcp_low_latency:
                        new_client.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
                        new_client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    else:
                        new_client.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x08)
                except OSError:  # unix socket
                    pass
                self._clients.append(gevent.spawn(self._client_poll, new_client))
        finally:
            with KillMask():
                gevent.killall(self._clients)

    def set_low_latency_signal(self, signal_name, value):
        """
        Set a tcp low latency on a signal name
        """
        if value:
            self._low_latency_signal.add(signal_name)
        else:
            try:
                self._low_latency_signal.remove(signal_name)
            except KeyError:
                pass

    def _client_poll(self, client_sock):
        unpacker = msgpack.Unpacker(raw=False, max_buffer_size=MAX_BUFFER_SIZE)
        lock = gevent.lock.RLock()
        if self._stream:

            def rx_event(value, signal):
                if not self._tcp_low_latency and signal in self._low_latency_signal:
                    with lock:
                        with switch_temporary_lowdelay(client_sock):
                            client_sock.sendall(
                                msgpack.packb((-1, (value, signal)), use_bin_type=True)
                            )
                else:
                    # standard signal with high throughput.
                    with lock:
                        client_sock.sendall(
                            msgpack.packb((-1, (value, signal)), use_bin_type=True)
                        )

            louie.connect(rx_event, sender=self._object)
        try:
            while True:
                msg = client_sock.recv(READ_BUFFER_SIZE)
                if not msg:
                    break
                unpacker.feed(msg)
                for u in unpacker:
                    call_id = u[0]
                    try:
                        return_values = self._call__(*u[1:])
                    except BaseException as e:
                        with lock:
                            client_sock.sendall(
                                msgpack.packb((call_id, e), use_bin_type=True)
                            )
                    else:
                        with lock:
                            try:
                                if self._tcp_low_latency:
                                    client_sock.sendall(
                                        msgpack.packb(
                                            (call_id, return_values), use_bin_type=True
                                        )
                                    )
                                else:
                                    with switch_temporary_lowdelay(client_sock):
                                        client_sock.sendall(
                                            msgpack.packb(
                                                (call_id, return_values),
                                                use_bin_type=True,
                                            )
                                        )
                            except Exception as e:
                                client_sock.sendall(
                                    msgpack.packb((call_id, e), use_bin_type=True)
                                )
        finally:
            client_sock.close()
            self._clients.remove(gevent.getcurrent())
            if self._stream:
                louie.disconnect(rx_event, sender=self._object)

    def _call__(self, code, args, kwargs):
        if code == "introspect":
            self._log.debug("rpc 'introspect'")
            return self._metadata
        elif code == "get_class":
            return self._get_object_class()
        else:
            name = args[0]
            if code == "call":
                value = getattr(self._object, name)(*args[1:], **kwargs)
                self._log.debug("rpc call %s() = %r", name, StripIt(value))
                return value
            elif code == "getattr":
                value = getattr(self._object, name)
                self._log.debug("rpc get %s = %r", name, StripIt(value))
                return value
            elif code == "setattr":
                value = args[1]
                self._log.debug("rpc set %s = %r", name, StripIt(value))
                return setattr(self._object, name, value)
            elif code == "delattr":
                self._log.debug("rpc del %s", name)
                return delattr(self._object, name)
            else:
                raise ServerError("Unknown call type {0!r}".format(code))


def Server(obj, stream=False, tcp_low_latency=False, **kwargs):
    """
    Create a rpc server for the given object with a pythonic API

    Args:
        obj: any python object
    Keyword Args:
        stream (bool): supply a stream listening to events coming from obj
    Return:
        a rpc server
    """
    return _ServerObject(obj, stream=stream, tcp_low_latency=tcp_low_latency)


# Client code


def _property(name, doc):
    def fget(self):
        return self._client._call__("getattr", (name,), {})

    def fset(self, value):
        self._client._call__("setattr", (name, value), {})

    def fdel(self):
        return self._client._call__("delattr", (name,), {})

    return property(fget=fget, fset=fset, fdel=fdel, doc=doc)


def _method(name, doc):
    if name == "__dir__":
        # need to handle __dir__ to make sure it returns a list, not a tuple
        def method(self):
            return list(self._client._call__("call", [name], {}))

    else:

        def method(self, *args, **kwargs):
            args = [name] + list(args)
            return self._client._call__("call", args, kwargs)

    method.__name__ = name
    method.__doc__ = doc
    return method


def _static_method(client, name, doc):
    def method(*args, **kwargs):
        args = [name] + list(args)
        return client._call__("call", args, kwargs)

    method.__name__ = name
    method.__doc__ = doc
    return staticmethod(method)


def _class_method(client, name, doc):
    def method(cls, *args, **kwargs):
        args = [name] + list(args)
        return client._call__("call", args, kwargs)

    method.__name__ = name
    method.__doc__ = doc
    return classmethod(method)


class _SubServer:
    def __init__(self, address):
        self.address = address


class RpcConnection:
    class wait_queue(object):
        def __init__(self, cnt, uniq_id):
            self._cnt = cnt
            self._event = gevent.event.Event()
            self._values = None
            self._uniq_id = uniq_id

        def __enter__(self):
            self._cnt._queues[self._uniq_id] = self
            return self

        def __exit__(self, *args):
            del self._cnt._queues[self._uniq_id]

        def get(self):
            self._event.wait()
            return self._values

        def put(self, values):
            self._values = values
            self._event.set()
            self._event.clear()

    def __init__(self, address, disconnect_callback, timeout=None):
        global_map.register(self, parents_list=["comms"], tag=f"rpc client:{address}")

        if address.startswith("tcp"):
            exp = re.compile("tcp://(.+?):([0-9]+)")
            m = exp.match(address)
            self.host = m.group(1)
            self.port = int(m.group(2))
        elif address.startswith("inproc") or address.startswith("ipc"):
            exp = re.compile("(inproc|ipc)://(.+)")
            m = exp.match(address)
            self.host = None
            self.port = m.group(2)

        self.__proxy = None
        self._proxy_lock = gevent.lock.Semaphore()
        self._lock = gevent.lock.Semaphore()
        self._address = address
        self._socket = None
        self._queues = dict()
        self._reading_task = None
        self._counter = itertools.cycle(range(2 ** 16))
        self._timeout = timeout
        self._disconnect_callback = disconnect_callback
        self._subclient = weakref.WeakValueDictionary()

    @property
    def address(self):
        return self._address

    def connect(self):
        if self._reading_task:
            return
        if self.host:
            self._socket = socket.socket()
            self._socket.connect((self.host, self.port))
            # On the client socket we set low delay socket
            # Disable Nagle and set TOS to low delay
            self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._socket.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        else:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(self.port)
        self._reading_task = gevent.spawn(self._raw_read)

    def get_class(self):
        p = self._proxy
        return self._call__("get_class", (), {})

    @property
    def _proxy(self):
        with gevent.Timeout(self._timeout):
            with self._proxy_lock:
                self.connect()
                if self.__proxy is None:
                    metadata = self._call__("introspect", (), {})

                    name = {metadata["name"]}
                    self._log = logging.getLogger(f"{__name__}.{name}")

                    members = dict(_client=self)

                    for name, info in metadata["members"].items():
                        if name.startswith("__") and name[2:-2] in SPECIAL_METHODS:
                            continue
                        name, mtype, doc = info["name"], info["type"], info["doc"]
                        if mtype == "attribute":
                            members[name] = _property(name, doc)
                        elif mtype == "method":
                            members[name] = _method(name, doc)
                        elif mtype == "staticmethod":
                            members[name] = _static_method(self, name, doc)
                        elif mtype == "classmethod":
                            members[name] = _class_method(self, name, doc)

                    self._real_class = metadata.pop("real_class", None)
                    klass = type(metadata["name"], (object,), members)
                    self.__proxy = klass()
                    global_map.register(self.__proxy, children_list=[self])
        return self.__proxy

    def _call__(self, code, args, kwargs):
        log_debug(self, f"rpc client ({self._address}): '{code}' args={args}")

        # Check if already return a sub client
        method_name = args[0] if args else ""
        value = self._subclient.get((code, method_name))
        if value is not None:
            return value

        uniq_id = numpy.uint16(next(self._counter))
        msg = msgpack.packb((uniq_id, code, args, kwargs), use_bin_type=True)
        with self.wait_queue(self, uniq_id) as w:
            while True:
                with self._lock:
                    # lock sendall to serialize concurrent client calls
                    self._socket.sendall(msg)
                value = w.get()
                if isinstance(value, BaseException):
                    # FIXME: checking the traceback is an approximation
                    # It would be better to know it was a raised exception
                    # from the server msg
                    if value.__traceback__ is None:
                        return value
                    else:
                        if isinstance(value, gevent.Timeout):
                            # the old exception cannot be re-raised => it blocks
                            raise gevent.Timeout(value.seconds, value.exception)
                        raise value
                elif isinstance(value, _SubServer):
                    sub_client = self._subclient.get(value.address)
                    if sub_client is None:
                        sub_client = Client(value.address)
                        self._subclient[value.address] = sub_client
                    self._subclient[(code, method_name)] = sub_client
                    return sub_client
                return value

    def _raw_read(self):
        unpacker = msgpack.Unpacker(raw=False, max_buffer_size=MAX_BUFFER_SIZE)
        exception = None
        try:
            while True:
                msg = self._socket.recv(READ_BUFFER_SIZE)
                if not msg:
                    # set socket to None, so another connect() will make a new one;
                    # do not close here since we are in another greenlet
                    self._socket = None
                    break
                unpacker.feed(msg)
                for m in unpacker:
                    call_id = m[0]
                    if call_id < 0:  # event:
                        value, signal = m[1]
                        louie.send(signal, self._proxy, value)
                    else:
                        return_values = m[1]
                        wq = self._queues.get(call_id)
                        if wq:
                            wq.put(return_values)
        except Exception as e:
            exception = e
            sys.excepthook(*sys.exc_info())
        finally:
            if (exception is None or not self._queues) and callable(
                self._disconnect_callback
            ):
                self._disconnect_callback()

    def close(self):
        if self._reading_task:
            self._reading_task.kill()
        if self._socket:
            self._socket.close()
        self._socket = None
        self._reading_task = None
        for client in self._subclient.values():
            client._rpc_connection.close()
        self._subclient = weakref.WeakValueDictionary()


class RpcProxy(proxy.Proxy):
    def __init__(self, rpc_connection):
        object.__setattr__(self, "_rpc_connection", rpc_connection)
        object.__setattr__(self, "_RpcProxy__class", None)
        super().__init__(lambda: rpc_connection._proxy)

    @property
    def __class__(self):
        if self.__class is None:
            try:
                object.__setattr__(
                    self, "_RpcProxy__class", self._rpc_connection.get_class()
                )
            except Exception:
                object.__setattr__(self, "_RpcProxy__class", type(self))
        return self.__class


def Client(address, timeout=3., disconnect_callback=None, **kwargs):
    rpc_connection = RpcConnection(address, disconnect_callback, timeout)
    proxy = RpcProxy(rpc_connection)
    return proxy
