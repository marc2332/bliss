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
        self._object = obj
        self._log = logging.getLogger(f"{__name__}.{type(obj).__name__}")
        self._metadata = _discover_object(obj)
        self._server_task = None
        self._clients = list()
        self._socket = None
        self._stream = stream
        self._metadata["stream"] = stream
        if isinstance(obj, proxy.Proxy):
            self._metadata["real_klass"] = type(obj.__wrapped__)
        elif not inspect.ismodule(obj):
            self._metadata["real_klass"] = type(obj)
        # if obj is a module it cannot be pickled, and 'real_klass' makes no sense
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
                    except Exception as e:
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

    def _call__(self, code, args, kwargs):
        if code == "introspect":
            self._log.debug("rpc 'introspect'")
            without_real_class = kwargs.get("without_real_class", False)
            if without_real_class is False:
                return self._metadata
            else:
                metadata = self._metadata.copy()
                metadata.pop("real_klass", None)
                return metadata
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


class _cnx(object):
    class Retry:
        def __init__(self, exception):
            self.exception = exception

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

    def __init__(self, address, disconnect_callback):

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

        self._address = address
        self._socket = None
        self._queues = dict()
        self._reading_task = None
        self.proxy = None
        self._counter = None
        self._timeout = 30.
        self._proxy = None
        self._klass = None
        self._real_klass = None
        self._class_member = list()
        self._disconnect_callback = disconnect_callback
        self._subclient = weakref.WeakValueDictionary()
        self._in_introspect = False

    def __del__(self):
        self.close()

    def connect(self):
        self.try_connect()

    def try_connect(self):
        try:
            return self._try_connect()
        except:
            if self._disconnect_callback is not None:
                self._disconnect_callback()
            raise

    def _try_connect(self):
        if self._socket is None:
            try:
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

                self._reading_task = gevent.spawn(self._raw_read, self._socket)
            except:
                self._socket = None
                raise
            self._counter = itertools.cycle(range(2 ** 16))
            if self._in_introspect:
                return

            try:
                self._in_introspect = True
                metadata = self._call__("introspect", (), {})
            finally:
                self._in_introspect = False

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

                if name.startswith("__"):
                    setattr(type(self.proxy), name, members[name])
                    self._class_member.append(name)
            klass = type(metadata["name"], (object,), members)
            self._klass = klass
            self._real_klass = metadata.get("real_klass")
            self._proxy = klass()

    def _call__(self, code, args, kwargs):
        timeout = kwargs.get("timeout", self._timeout)

        log_debug(self.proxy, f"rpc client ({self._address}): '{code}' args={args}")

        with gevent.Timeout(timeout):
            self.try_connect()
            # Check if already return a sub client
            method_name = args[0] if args else ""
            value = self._subclient.get((code, method_name))
            if value is not None:
                return value

            uniq_id = numpy.uint16(next(self._counter))
            msg = msgpack.packb((uniq_id, code, args, kwargs), use_bin_type=True)
            nb_retry_allowed = 1
            with self.wait_queue(self, uniq_id) as w:
                while True:
                    self._socket.sendall(msg)
                    value = w.get()
                    if isinstance(value, Exception):
                        # FIXME: checking the traceback is an approximation
                        # It would be better to know it was a raised exception
                        # from the server msg
                        if value.__traceback__ is None:
                            return value
                        else:
                            raise value
                    elif isinstance(value, self.Retry):
                        # check if the real class can be unpickled.
                        # if not AttributeError may be raise during introspect
                        if (
                            self._in_introspect
                            and code == "introspect"
                            and isinstance(value.exception, AttributeError)
                        ):
                            # let's ask to the server is **metadata** without the real_class object
                            msg = msgpack.packb(
                                (uniq_id, code, args, {"without_real_class": True}),
                                use_bin_type=True,
                            )
                        if value.exception is not None:
                            if nb_retry_allowed > 0:
                                nb_retry_allowed -= 1
                            else:
                                raise value.exception
                        self.try_connect()
                        continue
                    elif isinstance(value, _SubServer):
                        sub_client = self._subclient.get(value.address)
                        if sub_client is None:
                            sub_client = Client(value.address)
                            self._subclient[value.address] = sub_client
                        self._subclient[(code, method_name)] = sub_client
                        return sub_client
                    return value

    def _raw_read(self, socket):
        unpacker = msgpack.Unpacker(raw=False, max_buffer_size=MAX_BUFFER_SIZE)
        exception = None
        try:
            while True:
                msg = socket.recv(READ_BUFFER_SIZE)
                if not msg:
                    break
                unpacker.feed(msg)
                for m in unpacker:
                    call_id = m[0]
                    if call_id < 0:  # event:
                        value, signal = m[1]
                        louie.send(signal, self.proxy, value)
                    else:
                        return_values = m[1]
                        wq = self._queues.get(call_id)
                        if wq:
                            wq.put(return_values)
        except Exception as e:
            exception = e
        finally:
            try:
                socket.close()
            except:
                pass
            self._socket = None
            self._reading_task = None
            for w in self._queues.values():
                w.put(self.Retry(exception))
            for name in self._class_member:
                delattr(type(self.proxy), name)
            self._class_member = list()
            if self._disconnect_callback is not None:
                self._disconnect_callback()

    def close(self):
        if self._reading_task:
            self._reading_task.kill()
        for client in self._subclient.values():
            client.close()
        self._subclient = weakref.WeakValueDictionary()

    @property
    def connection_address(self):
        return self._address


def Client(address, timeout=30., disconnect_callback=None, **kwargs):
    client = _cnx(address, disconnect_callback)

    class Meta(type):
        def __getattribute__(cls, *args):
            try:
                client.try_connect()
            except:
                # in case of isinstance and
                # not connected set type like None
                if args[0] == "__class__":
                    return type(None)
                raise
            if args[0] == "__class__" and client._real_klass is not None:
                return client._real_klass

            return_val = client._klass.__getattribute__(client._klass, *args)
            return return_val

    class _Proxy(object, metaclass=Meta):
        def __init__(self):
            """
            Create a rpc client with a pythonic API

            Args:
                address: connection address (ex: 'tcp://lid00c:8989')
            Return:
                a rpc client

            """
            kwargs.setdefault("connect_to", address)

            client.proxy = self

        def __getattribute__(self, name):
            if name in ["close", "connect", "connection_address"]:
                return getattr(client, name)

            try:
                client.try_connect()
            except FileNotFoundError:
                # in case of disconnection of a local client
                # The uds socket file has been removed
                # In that case can't return a best answer than:
                raise AttributeError(f"{name}, not connected")
            except:
                # in case of isinstance and
                # not connected don't know the type
                # return in that case _Proxy class
                if name == "__class__":
                    return type(self)
                raise
            if name == "__class__" and client._real_klass is not None:
                return client._real_klass
            return client._proxy.__getattribute__(name)

        def __setattr__(self, name, value):
            client.try_connect()
            client._proxy.__setattr__(name, value)

    return _Proxy()
