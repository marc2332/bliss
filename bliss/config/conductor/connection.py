# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import weakref
import os, sys
import gevent
from gevent import socket, select, event, queue
from . import protocol
import redis
import netifaces


class StolenLockException(RuntimeError):
    """This exception is raise in case of a stolen lock"""


def ip4_broadcast_addresses(default_route_only=False):
    ip_list = []
    # get default route interface, if any
    gws = netifaces.gateways()
    try:
        if default_route_only:
            interfaces = [gws["default"][netifaces.AF_INET][1]]
        else:
            interfaces = netifaces.interfaces()
        for interface in interfaces:
            for link in netifaces.ifaddresses(interface).get(netifaces.AF_INET, []):
                ip_list.append(link.get("broadcast"))
    except Exception:
        pass

    return [_f for _f in ip_list if _f]


def ip4_broadcast_discovery(udp):
    for addr in ip4_broadcast_addresses():
        udp.sendto(b"Hello", (addr, protocol.DEFAULT_UDP_SERVER_PORT))


def compare_hosts(host1, host2):
    if host1 == host2:
        return True
    if host1 == "localhost" and host2 == socket.gethostname():
        return True
    if host2 == "localhost" and host1 == socket.gethostname():
        return True
    if socket.gethostbyname(host1) == socket.gethostbyname(host2):
        return True
    return False


def check_connect(func):
    def f(self, *args, **keys):
        self.connect()
        return func(self, *args, **keys)

    return f


class ConnectionException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


class Connection(object):
    class WaitingLock(object):
        def __init__(self, cnt, priority, device_name):
            self._cnt = weakref.ref(cnt)
            raw_names = [name.encode() for name in device_name]
            self._msg = b"%d|%s" % (priority, b"|".join(raw_names))
            self._queue = queue.Queue()

        def msg(self):
            return self._msg

        def get(self):
            return self._queue.get()

        def __enter__(self):
            cnt = self._cnt()
            pm = cnt._pending_lock.get(self._msg, [])
            if not pm:
                cnt._pending_lock[self._msg] = [self._queue]
            else:
                pm.append(self._queue)
            return self

        def __exit__(self, *args):
            cnt = self._cnt()
            pm = cnt._pending_lock.pop(self._msg, [])
            if pm:
                try:
                    pm.remove(self._queue)
                except ValueError:
                    pass
                cnt._pending_lock[self._msg] = pm

    class WaitingQueue(object):
        def __init__(self, cnt):
            self._cnt = weakref.ref(cnt)
            self._message_key = str(cnt._message_key).encode()
            cnt._message_key += 1
            self._queue = queue.Queue()

        def message_key(self):
            return self._message_key

        def get(self):
            return self._queue.get()

        def queue(self):
            return self._queue

        def __enter__(self):
            cnt = self._cnt()
            cnt._message_queue[self._message_key] = self._queue
            return self

        def __exit__(self, *args):
            cnt = self._cnt()
            cnt._message_queue.pop(self._message_key, None)

    def __init__(self, host=None, port=None):
        self._socket = None
        if host is None:
            host = os.environ.get("BEACON_HOST")
        if host is not None and ":" in host:
            host, port = host.split(":")
        if port is None:
            port = os.environ.get("BEACON_PORT")
        if port is not None:
            try:
                port = int(port)
            except ValueError:
                if not os.access(port, os.R_OK):
                    raise RuntimeError("port can be a tcp port (int) or unix socket")

        self._host = host
        self._port = port
        self._pending_lock = {}
        self._uds_query_event = event.Event()
        self._redis_query_event = event.Event()
        self._message_key = 0
        self._message_queue = {}
        self._redis_connection = {}
        self._clean()
        self._fd = None
        self._raw_read_task = None
        self._greenlet_to_lockobjects = weakref.WeakKeyDictionary()

    def close(self):
        if self._fd:
            self._fd.close()
            self._fd = None
        if self._raw_read_task is not None:
            self._raw_read_task.join()
            self._raw_read_task = None

    @property
    def uds(self):
        if sys.platform in ["win32", "cygwin"]:
            return False
        else:
            try:
                int(self._port)
            except ValueError:
                return self._port
            else:
                return None

    def connect(self):
        # Already connected
        if self._fd is not None:
            return

        # Address undefined
        if self._port is None or self._host is None:
            self._host, self._port = self._discovery(self._host)

        # UDS connection
        if self.uds:
            self._fd = self._uds_connect(self.uds)
        # TCP connection
        else:
            self._fd = self._tcp_connect(self._host, self._port)

        # Spawn read task
        self._raw_read_task = gevent.spawn(self._raw_read)

        # Run the UDS query
        if self.uds is None:
            self._uds_query()

    def _discovery(self, host, timeout=3.0):
        # Manage timeout
        if timeout < 0:
            if host is not None:
                raise RuntimeError(
                    "Conductor server on host `{}' does not reply (check beacon server)".format(
                        host
                    )
                )
            raise RuntimeError(
                "Could not find any conductor "
                "(check Beacon server and BEACON_HOST environment variable)"
            )
        started = time.time()

        # Create UDP socket
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.settimeout(0.2)

        # Send discovery
        address_list = [host] if host is not None else ip4_broadcast_addresses(True)
        for addr in address_list:
            try:
                udp.sendto(b"Hello", (addr, protocol.DEFAULT_UDP_SERVER_PORT))
            except socket.gaierror:
                raise ConnectionException("Host `%s' is not found in DNS" % addr)

        # Loop over UDP messages
        try:
            for message in iter(lambda: udp.recv(8192), None):

                # Decode message
                raw_host, raw_port = message.split(b"|")
                received_host = raw_host.decode()
                received_port = int(raw_port.decode())

                # Received host doesn't match the host
                if host is not None and not compare_hosts(host, received_host):
                    continue

                # A matching host has been found
                return received_host, received_port

        # Try again
        except socket.timeout:
            timeout -= time.time() - started
            return self._discovery(host, timeout=timeout)

    def _tcp_connect(self, host, port):
        fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        fd.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        try:
            fd.connect((host, port))
        except IOError:
            raise RuntimeError(
                "Conductor server on host `{}:{}' does not reply (check beacon server)".format(
                    host, port
                )
            )
        return fd

    def _uds_connect(self, uds_path):
        fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        fd.connect(uds_path)
        return fd

    def _uds_query(self, timeout=1.0):
        self._uds_query_event.clear()
        self._fd.sendall(
            protocol.message(protocol.UDS_QUERY, socket.gethostname().encode())
        )
        self._uds_query_event.wait(timeout)

    @check_connect
    def lock(self, devices_name, **params):
        priority = params.get("priority", 50)
        timeout = params.get("timeout", 10)
        if len(devices_name) == 0:
            return  # don't need to ask ;)
        with self.WaitingLock(self, priority, devices_name) as wait_lock:
            with gevent.Timeout(
                timeout, RuntimeError("lock timeout (%s)" % str(devices_name))
            ):
                while 1:
                    self._fd.sendall(protocol.message(protocol.LOCK, wait_lock.msg()))
                    status = wait_lock.get()
                    if status == protocol.LOCK_OK_REPLY:
                        break
        locked_objects = self._greenlet_to_lockobjects.setdefault(
            gevent.getcurrent(), dict()
        )
        for device in devices_name:
            nb_lock = locked_objects.get(device, 0)
            locked_objects[device] = nb_lock + 1

    @check_connect
    def unlock(self, devices_name, **params):
        timeout = params.get("timeout", 1)
        priority = params.get("priority", 50)
        if len(devices_name) == 0:
            return
        raw_names = [name.encode() for name in devices_name]
        msg = b"%d|%s" % (priority, b"|".join(raw_names))
        with gevent.Timeout(
            timeout, RuntimeError("unlock timeout (%s)" % str(devices_name))
        ):
            self._fd.sendall(protocol.message(protocol.UNLOCK, msg))
        locked_objects = self._greenlet_to_lockobjects.setdefault(
            gevent.getcurrent(), dict()
        )
        max_lock = 0
        for device in devices_name:
            nb_lock = locked_objects.get(device, 0)
            nb_lock -= 1
            if nb_lock > max_lock:
                max_lock = nb_lock
            locked_objects[device] = nb_lock
        if max_lock <= 0:
            self._greenlet_to_lockobjects.pop(gevent.getcurrent(), None)

    @check_connect
    def get_redis_connection_address(self, timeout=1.0):
        if self._redis_host is None:
            with gevent.Timeout(
                timeout, RuntimeError("Can't get redis connection information")
            ):
                while self._redis_host is None:
                    self._redis_query_event.clear()
                    self._fd.sendall(protocol.message(protocol.REDIS_QUERY))
                    self._redis_query_event.wait()

        return self._redis_host, self._redis_port

    @check_connect
    def get_redis_connection(self, db=0):
        cnx = self._redis_connection.get(db)
        if cnx is None:
            executable = os.path.basename(sys.argv[0]).replace(os.path.sep, "")
            my_name = "{0}:{1}".format(executable, os.getpid())
            cnx = self.create_redis_connection(db=db)
            cnx.client_setname(my_name)
            self._redis_connection[db] = cnx
        return cnx

    def clean_all_redis_connection(self):
        for cnx in self._redis_connection.values():
            cnx.connection_pool.disconnect()
        self._redis_connection = {}

    def create_redis_connection(self, db=0, address=None):
        if address is None:
            address = self.get_redis_connection_address()
        host, port = address
        if host == "localhost":
            return redis.Redis(unix_socket_path=port, db=db)
        return redis.Redis(host=host, port=port, db=db)

    @check_connect
    def get_config_file(self, file_path, timeout=1.0):
        with gevent.Timeout(timeout, RuntimeError("Can't get configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), file_path.encode())
                self._fd.sendall(protocol.message(protocol.CONFIG_GET_FILE, msg))
                value = wq.get()
                if isinstance(value, RuntimeError):
                    raise value
                else:
                    return value

    @check_connect
    def get_config_db_tree(self, base_path="", timeout=1.0):
        with gevent.Timeout(timeout, RuntimeError("Can't get configuration tree")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), base_path.encode())
                self._fd.sendall(protocol.message(protocol.CONFIG_GET_DB_TREE, msg))
                value = wq.get()
                if isinstance(value, RuntimeError):
                    raise value
                else:
                    import json

                    return json.loads(value)

    @check_connect
    def remove_config_file(self, file_path, timeout=1.0):
        with gevent.Timeout(timeout, RuntimeError("Can't remove configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), file_path.encode())
                self._fd.sendall(protocol.message(protocol.CONFIG_REMOVE_FILE, msg))
                for rx_msg in wq.queue():
                    print(rx_msg)

    @check_connect
    def move_config_path(self, src_path, dst_path, timeout=1.0):
        with gevent.Timeout(timeout, RuntimeError("Can't move configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s|%s" % (
                    wq.message_key(),
                    src_path.encode(),
                    dst_path.encode(),
                )
                self._fd.sendall(protocol.message(protocol.CONFIG_MOVE_PATH, msg))
                for rx_msg in wq.queue():
                    print(rx_msg)

    @check_connect
    def get_config_db(self, base_path="", timeout=30.0):
        return_files = []
        with gevent.Timeout(timeout, RuntimeError("Can't get configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), base_path.encode())
                self._fd.sendall(
                    protocol.message(protocol.CONFIG_GET_DB_BASE_PATH, msg)
                )
                for rx_msg in wq.queue():
                    if isinstance(rx_msg, RuntimeError):
                        raise rx_msg
                    file_path, file_value = self._get_msg_key(rx_msg)
                    if file_path is None:
                        continue
                    return_files.append((file_path.decode(), file_value.decode()))
        return return_files

    @check_connect
    def set_config_db_file(self, file_path, content, timeout=3.0):
        with gevent.Timeout(timeout, RuntimeError("Can't set config file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s|%s" % (
                    wq.message_key(),
                    file_path.encode(),
                    content.encode(),
                )
                self._fd.sendall(protocol.message(protocol.CONFIG_SET_DB_FILE, msg))
                for rx_msg in wq.queue():
                    raise rx_msg

    @check_connect
    def get_python_modules(self, base_path="", timeout=3.0):
        return_module = []
        with gevent.Timeout(timeout, RuntimeError("Can't get python modules")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), base_path.encode())
                self._fd.sendall(
                    protocol.message(protocol.CONFIG_GET_PYTHON_MODULE, msg)
                )
                for rx_msg in wq.queue():
                    if isinstance(rx_msg, RuntimeError):
                        raise rx_msg
                    module_name, full_path = self._get_msg_key(rx_msg)
                    return_module.append((module_name.decode(), full_path.decode()))
        return return_module

    def _lock_mgt(self, fd, messageType, message):
        if messageType == protocol.LOCK_OK_REPLY:
            events = self._pending_lock.get(message, [])
            if not events:
                fd.sendall(protocol.message(protocol.UNLOCK, message))
            else:
                e = events.pop(0)
                e.put(messageType)
            return True
        elif messageType == protocol.LOCK_RETRY:
            for m, l in self._pending_lock.items():
                for e in l:
                    e.put(messageType)
            return True
        elif messageType == protocol.LOCK_STOLEN:
            stolen_object_lock = set(message.split(b"|"))
            greenlet_to_objects = self._greenlet_to_lockobjects.copy()
            for greenlet, locked_objects in greenlet_to_objects.items():
                locked_object_name = set(
                    (name for name, nb_lock in locked_objects.items() if nb_lock > 0)
                )
                if locked_object_name.intersection(stolen_object_lock):
                    try:
                        greenlet.kill(exception=StolenLockException)
                    except AttributeError:
                        pass
            fd.sendall(protocol.message(protocol.LOCK_STOLEN_OK_REPLY, message))
            return True
        return False

    def _get_msg_key(self, message):
        pos = message.find(b"|")
        if pos < 0:
            return None, None
        return message[:pos], message[pos + 1 :]

    def _raw_read(self):
        try:
            data = b""
            while True:
                raw_data = self._fd.recv(16 * 1024)
                if not raw_data:
                    break
                data = b"%s%s" % (data, raw_data)
                while data:
                    try:
                        messageType, message, data = protocol.unpack_message(data)
                    except protocol.IncompleteMessage:
                        break
                    try:
                        # print 'rx',messageType
                        if self._lock_mgt(self._fd, messageType, message):
                            continue
                        elif messageType in (
                            protocol.CONFIG_GET_FILE_OK,
                            protocol.CONFIG_GET_DB_TREE_OK,
                            protocol.CONFIG_DB_FILE_RX,
                            protocol.CONFIG_GET_PYTHON_MODULE_RX,
                        ):
                            message_key, value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None:
                                queue.put(value)
                        elif messageType in (
                            protocol.CONFIG_GET_FILE_FAILED,
                            protocol.CONFIG_DB_FAILED,
                            protocol.CONFIG_SET_DB_FILE_FAILED,
                            protocol.CONFIG_GET_DB_TREE_FAILED,
                            protocol.CONFIG_REMOVE_FILE_FAILED,
                            protocol.CONFIG_MOVE_PATH_FAILED,
                            protocol.CONFIG_GET_PYTHON_MODULE_FAILED,
                        ):
                            message_key, value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None:
                                queue.put(RuntimeError(value.decode()))
                        elif messageType in (
                            protocol.CONFIG_DB_END,
                            protocol.CONFIG_SET_DB_FILE_OK,
                            protocol.CONFIG_REMOVE_FILE_OK,
                            protocol.CONFIG_MOVE_PATH_OK,
                            protocol.CONFIG_GET_PYTHON_MODULE_END,
                        ):
                            message_key, value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None:
                                queue.put(StopIteration)
                        elif messageType == protocol.REDIS_QUERY_ANSWER:
                            host, port = message.split(b":")
                            self._redis_host = host.decode()
                            self._redis_port = port.decode()
                            self._redis_query_event.set()
                        elif messageType == protocol.UDS_OK:
                            try:
                                uds_path = message.decode()
                                fd = self._uds_connect(uds_path)
                            except socket.error:
                                raise
                            else:
                                self._fd.close()
                                self._fd = fd
                                self._port = uds_path
                            finally:
                                self._uds_query_event.set()
                        elif messageType == protocol.UDS_FAILED:
                            self._uds_query_event.set()
                        elif messageType == protocol.UNKNOW_MESSAGE:
                            message_key, value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            error = RuntimeError(
                                "Beacon server don't know this command (%s)" % value
                            )
                            if queue is not None:
                                queue.put(error)
                    except:
                        sys.excepthook(*sys.exc_info())
        except socket.error:
            pass
        except:
            sys.excepthook(*sys.exc_info())
        finally:
            if self._fd:
                self._fd.close()
                self._fd = None
            self._clean()

    def _clean(self):
        self._redis_host = None
        self._redis_port = None
        for db, redis_cnx in self._redis_connection.items():
            redis_cnx.connection_pool.disconnect()
        self._redis_connection = {}

    @check_connect
    def __str__(self):
        return "Connection({0}:{1})".format(self._host, self._port)
