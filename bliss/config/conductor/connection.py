# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import weakref
import os, sys
import gevent
import gevent.lock
from gevent import socket, select, event, queue
from . import protocol
import netifaces
from functools import wraps
import warnings
from collections import namedtuple

from bliss.common.greenlet_utils import protect_from_kill, AllowKill
from bliss.config.conductor import redis_connection


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
    @wraps(func)
    def f(self, *args, **keys):
        self.connect()
        return func(self, *args, **keys)

    return f


class ConnectionException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)


RedisPoolId = namedtuple("RedisProxyId", ["db"])
RedisProxyId = namedtuple("RedisProxyId", ["db", "caching"])


class Connection:
    """A Beacon connection is created and destroyed like this:

        connection = Connection(host=..., port=...)
        connection.connect()  # not required
        connection.close()  # closes all Redis connections as well

    When `host` is not provided, it falls back to environment variable BEACON_HOST.
    When `port` is not provided, it falls back to environment variable BEACON_PORT.
    When either does not have a fallback, use UDP broadcasting to find Beacon.

    The Beacon connection also manages all Redis connections.
    Use `get_redis_proxy` to create a connection or use an existing one.
    Use `close_all_redis_connections` to close all Redis connections.

    Beacon locks: the methods `lock`, `unlock` and  `who_locked` provide
    a mechanism to acquire and release locks in the Beacon server.

    Beacon manages configuration files (YAML) and python modules. This class
    allows fetching and manipulating those.
    """

    CLIENT_NAME = f"{socket.gethostname()}:{os.getpid()}"

    class WaitingLock:
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

        # Beacon connection
        self._host = host
        self._port = port
        # self._port_number is here to keep trace of port number
        # as self._port can be replaced by unix socket name.
        self._port_number = port
        self._socket = None
        self._connect_lock = gevent.lock.Semaphore()
        self._connected = gevent.event.Event()
        self._send_lock = gevent.lock.Semaphore()
        self._uds_query_event = event.Event()
        self._redis_query_event = event.Event()
        self._message_key = 0
        self._message_queue = {}
        self._clean_beacon_cache()
        self._raw_read_task = None

        # Beacon locks
        self._pending_lock = {}
        # Count how many time an object has been locked in the
        # current process per greenlet:
        self._lock_counters = weakref.WeakKeyDictionary()  # {Greenlet -> {str: int}}

        # Redis connections
        self._get_redis_lock = gevent.lock.Semaphore()

        # Keep hard references to all shared Redis proxies
        # (these proxies don't hold a `redis.Redis.Connection` instance)
        self._shared_redis_proxies = {}  # {RedisProxyId: RedisDbProxyBase}

        # Keep weak references to all shared Redis connection pools:
        self._redis_connection_pools = (
            weakref.WeakValueDictionary()
        )  # {RedisPoolId: RedisDbConnectionPool}

        # Keep weak references to all cached Redis proxies which are not
        # reused (although they could be but their cache with kep growing)
        self._non_shared_redis_proxies = weakref.WeakSet()  # {RedisDbProxyBase}

        # Hard references to the connection pools are held by the
        # Redis proxies themselves. Connections of RedisDbConnectionPool
        # are closed upon garbage collection of RedisDbConnectionPool. So
        # when the proxies too a pool are the only ones having a hard
        # reference too that pool, the connections are closed when all
        # proxies are garbage collected.

    def close(self, timeout=None):
        """Disconnection from Beacon and Redis
        """
        if self._raw_read_task is not None:
            self._raw_read_task.kill(timeout=timeout)
            self._raw_read_task = None

    @property
    def uds(self):
        """
        False: UDS not supported by this platform
        None: Port not defined
        str: Port number
        """
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
        """Find the Beacon server (if not already known) and make the
        TCP or UDS connection.
        """
        with self._connect_lock:
            if self._connected.is_set():
                return
            # Address undefined
            if self._port is None or self._host is None:
                self._host, self._port = self._discovery(self._host)

            # UDS connection
            if self.uds:
                self._socket = self._uds_connect(self.uds)
            # TCP connection
            else:
                self._socket = self._tcp_connect(self._host, self._port)

            # Spawn read task
            self._raw_read_task = gevent.spawn(self._raw_read)
            self._raw_read_task.name = "BeaconListenTask"

            # Run the UDS query
            if self.uds is None:
                self._uds_query()

            self.on_connected()

            self._connected.set()

    def on_connected(self):
        """Executed whenever a new connection is made
        """
        self._set_get_clientname(name=self.CLIENT_NAME, timeout=3)

    def _discovery(self, host, timeout=3.0):
        # Manage timeout
        if timeout < 0:
            if host is not None:
                raise RuntimeError(
                    f"Conductor server on host `{host}' does not reply (check beacon server)"
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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        try:
            sock.connect((host, port))
        except IOError:
            raise RuntimeError(
                "Conductor server on host `{}:{}' does not reply (check beacon server)".format(
                    host, port
                )
            )
        return sock

    def _uds_connect(self, uds_path):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(uds_path)
        return sock

    def _uds_query(self, timeout=3.0):
        self._uds_query_event.clear()
        self._sendall(
            protocol.message(protocol.UDS_QUERY, socket.gethostname().encode())
        )
        self._uds_query_event.wait(timeout)

    @check_connect
    def lock(self, *devices_name, **params):
        priority = params.get("priority", 50)
        timeout = params.get("timeout", 10)
        if not devices_name:
            return
        with self.WaitingLock(self, priority, devices_name) as wait_lock:
            with gevent.Timeout(
                timeout, RuntimeError("lock timeout (%s)" % str(devices_name))
            ):
                while True:
                    self._sendall(protocol.message(protocol.LOCK, wait_lock.msg()))
                    status = wait_lock.get()
                    if status == protocol.LOCK_OK_REPLY:
                        break
        self._increment_lock_counters(devices_name)

    @check_connect
    def unlock(self, *devices_name, **params):
        timeout = params.get("timeout", 1)
        priority = params.get("priority", 50)
        if not devices_name:
            return
        raw_names = [name.encode() for name in devices_name]
        msg = b"%d|%s" % (priority, b"|".join(raw_names))
        with gevent.Timeout(
            timeout, RuntimeError("unlock timeout (%s)" % str(devices_name))
        ):
            self._sendall(protocol.message(protocol.UNLOCK, msg))
        self._decrement_lock_counters(devices_name)

    def _increment_lock_counters(self, devices_name):
        """Keep track of locking per greenlet
        """
        locked_objects = self._lock_counters.setdefault(gevent.getcurrent(), dict())
        for device in devices_name:
            nb_lock = locked_objects.get(device, 0)
            locked_objects[device] = nb_lock + 1

    def _decrement_lock_counters(self, devices_name):
        """Keep track of locking per greenlet
        """
        locked_objects = self._lock_counters.setdefault(gevent.getcurrent(), dict())
        max_lock = 0
        for device in devices_name:
            nb_lock = locked_objects.get(device, 0)
            nb_lock -= 1
            if nb_lock > max_lock:
                max_lock = nb_lock
            locked_objects[device] = nb_lock
        if max_lock <= 0:
            self._lock_counters.pop(gevent.getcurrent(), None)

    @check_connect
    def get_redis_connection_address(self, timeout=3.0):
        """Get the Redis host and port from Beacon. Cached for the duration
        of the Beacon connection.
        """
        if self._redis_host is None:
            with gevent.Timeout(
                timeout, RuntimeError("Can't get redis connection information")
            ):
                while self._redis_host is None:
                    self._redis_query_event.clear()
                    self._sendall(protocol.message(protocol.REDIS_QUERY))
                    self._redis_query_event.wait()

        return self._redis_host, self._redis_port

    def _get_redis_conn_pool(self, proxyid: RedisProxyId):
        """Get a Redis connection pool (create when it does not exist yet)
        for the db.

        :param RedisProxyId proxyid:
        :returns RedisDbConnectionPool:
        """
        poolid = RedisPoolId(db=proxyid.db)
        pool = self._redis_connection_pools.get(poolid)
        if pool is None:
            pool = self._create_redis_conn_pool(poolid)
            self._redis_connection_pools[poolid] = pool
        return pool

    def _create_redis_conn_pool(self, proxyid: RedisProxyId):
        """
        :param RedisProxyId proxyid:
        :returns RedisDbConnectionPool:
        """
        address = self.get_redis_connection_address()
        if proxyid.db == 1:
            try:
                address = self.get_redis_data_server_connection_address()
            except RuntimeError:  # Service not running on beacon server
                pass

        host, port = address
        if host == "localhost":
            redis_url = f"unix://{port}"
        else:
            redis_url = f"redis://{host}:{port}"
        return redis_connection.create_connection_pool(
            redis_url, proxyid.db, client_name=self.CLIENT_NAME
        )

    def _get_shared_redis_proxy(self, proxyid: RedisProxyId):
        """Get a reusabed proxy and create it when it doesn't exist.
        """
        with self._get_redis_lock:
            proxy = self._shared_redis_proxies.get(proxyid)
            if proxy is None:
                pool = self._get_redis_conn_pool(proxyid)
                proxy = pool.create_proxy(caching=proxyid.caching)
                self._shared_redis_proxies[proxyid] = proxy
            return proxy

    def _get_non_shared_redis_proxy(self, proxyid: RedisProxyId):
        """Get a reusabed proxy and create it when it doesn't exist.
        """
        with self._get_redis_lock:
            pool = self._get_redis_conn_pool(proxyid)
            proxy = pool.create_proxy(caching=proxyid.caching)
            self._non_shared_redis_proxies.add(proxy)
            return proxy

    def get_redis_connection(self, **kw):
        warnings.warn("Use 'get_redis_proxy' instead", FutureWarning)
        return self.get_redis_proxy(**kw)

    def get_redis_proxy(self, db=0, caching=False, shared=True):
        """Get a greenlet-safe proxy to a Redis database.

        :param int db: Redis database too which we need a proxy
        :param bool caching: client-side caching
        :param bool shared: use a shared proxy held by the Beacon connection
        """
        proxyid = RedisProxyId(db=db, caching=caching)
        if shared:
            return self._get_shared_redis_proxy(proxyid)
        else:
            return self._get_non_shared_redis_proxy(proxyid)

    def close_all_redis_connections(self):
        # To close `redis.connection.Connection` you need to call its
        # `disconnect` method (also called on garbage collection).
        #
        # Connection pools have a `disconnect` method that disconnect
        # all their connections, which means close and destroy their
        # socket instances.
        #
        # Note: closing a proxy will not close any connections
        proxies = list(self._non_shared_redis_proxies)
        proxies.extend(self._shared_redis_proxies.values())
        self._shared_redis_proxies = dict()
        self._non_shared_redis_proxies = weakref.WeakSet()
        for proxy in proxies:
            proxy.close()
            proxy.connection_pool.disconnect()

    def clean_all_redis_connection(self):
        warnings.warn("Use 'close_all_redis_connections' instead", FutureWarning)
        self.close_all_redis_connections()

    @check_connect
    def get_config_file(self, file_path, timeout=3.0):
        with gevent.Timeout(timeout, RuntimeError("Can't get configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), file_path.encode())
                self._sendall(protocol.message(protocol.CONFIG_GET_FILE, msg))
                # self._socket.sendall(protocol.message(protocol.CONFIG_GET_FILE, msg))
                value = wq.get()
                if isinstance(value, RuntimeError):
                    raise value
                else:
                    return value

    @check_connect
    def get_config_db_tree(self, base_path="", timeout=3.0):
        with gevent.Timeout(timeout, RuntimeError("Can't get configuration tree")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), base_path.encode())
                self._sendall(protocol.message(protocol.CONFIG_GET_DB_TREE, msg))
                value = wq.get()
                if isinstance(value, RuntimeError):
                    raise value
                else:
                    import json

                    return json.loads(value)

    @check_connect
    def remove_config_file(self, file_path, timeout=3.0):
        with gevent.Timeout(timeout, RuntimeError("Can't remove configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), file_path.encode())
                self._sendall(protocol.message(protocol.CONFIG_REMOVE_FILE, msg))
                for rx_msg in wq.queue():
                    print(rx_msg)

    @check_connect
    def move_config_path(self, src_path, dst_path, timeout=3.0):
        with gevent.Timeout(timeout, RuntimeError("Can't move configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s|%s" % (
                    wq.message_key(),
                    src_path.encode(),
                    dst_path.encode(),
                )
                self._sendall(protocol.message(protocol.CONFIG_MOVE_PATH, msg))
                for rx_msg in wq.queue():
                    print(rx_msg)

    @check_connect
    def get_config_db(self, base_path="", timeout=30.0):
        return_files = []
        with gevent.Timeout(timeout, RuntimeError("Can't get configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), base_path.encode())
                self._sendall(protocol.message(protocol.CONFIG_GET_DB_BASE_PATH, msg))
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
                self._sendall(protocol.message(protocol.CONFIG_SET_DB_FILE, msg))
                for rx_msg in wq.queue():
                    raise rx_msg

    @check_connect
    def get_python_modules(self, base_path="", timeout=3.0):
        return_module = []
        with gevent.Timeout(timeout, RuntimeError("Can't get python modules")):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), base_path.encode())
                self._sendall(protocol.message(protocol.CONFIG_GET_PYTHON_MODULE, msg))
                for rx_msg in wq.queue():
                    if isinstance(rx_msg, RuntimeError):
                        raise rx_msg
                    module_name, full_path = self._get_msg_key(rx_msg)
                    return_module.append((module_name.decode(), full_path.decode()))
        return return_module

    @check_connect
    def get_log_server_address(self, timeout=3.0):
        """Get the log host and port from Beacon. Cached for the duration
        of the Beacon connection.
        """
        if self._log_server_host is None:
            with gevent.Timeout(
                timeout, RuntimeError("Can't retrieve log server port")
            ):
                with self.WaitingQueue(self) as wq:
                    msg = b"%s|" % wq.message_key()
                    self._socket.sendall(
                        protocol.message(protocol.LOG_SERVER_ADDRESS_QUERY, msg)
                    )
                    for rx_msg in wq.queue():
                        if isinstance(rx_msg, RuntimeError):
                            raise rx_msg
                        host, port = self._get_msg_key(rx_msg)
                        self._log_server_host = host.decode()
                        self._log_server_port = port.decode()
                        break
        return self._log_server_host, self._log_server_port

    @check_connect
    def get_redis_data_server_connection_address(self, timeout=3.):
        """Get the Redis data host and port from Beacon. Cached for the duration
        of the Beacon connection.
        """
        if self._redis_data_host is None:
            with gevent.Timeout(
                timeout, RuntimeError("Can't get redis data server information")
            ):
                with self.WaitingQueue(self) as wq:
                    msg = b"%s|" % wq.message_key()
                    self._socket.sendall(
                        protocol.message(protocol.REDIS_DATA_SERVER_QUERY, msg)
                    )
                    for rx_msg in wq.queue():
                        if isinstance(rx_msg, RuntimeError):
                            raise rx_msg
                        host, port = rx_msg.split(b"|")
                        self._redis_data_host = host.decode()
                        self._redis_data_port = port.decode()
                        break
        return self._redis_data_host, self._redis_data_port

    @check_connect
    def set_client_name(self, name, timeout=3.0):
        self._set_get_clientname(name=name, timeout=timeout)

    @check_connect
    def get_client_name(self, timeout=3.0):
        return self._set_get_clientname(timeout=timeout)

    def who_locked(self, *names, timeout=3.0):
        name2client = dict()
        with gevent.Timeout(timeout, RuntimeError("Can't get who lock client name")):
            with self.WaitingQueue(self) as wq:
                raw_names = [b"%s" % wq.message_key()] + [n.encode() for n in names]
                msg = b"|".join(raw_names)
                self._sendall(protocol.message(protocol.WHO_LOCKED, msg))
                for rx_msg in wq.queue():
                    if isinstance(rx_msg, RuntimeError):
                        raise rx_msg
                    name, client_info = rx_msg.split(b"|")
                    name2client[name.decode()] = client_info.decode()
        return name2client

    def _set_get_clientname(self, name=None, timeout=3.):
        """Give a name for this client to the Beacon server (optional)
        and return the name under which this client is know by Beacon.
        """
        if name:
            timeout_msg = "Can't set client name"
            msg_type = protocol.CLIENT_SET_NAME
            name = name.encode()
        else:
            timeout_msg = "Can't get client name"
            msg_type = protocol.CLIENT_GET_NAME
            name = b""
        with gevent.Timeout(timeout, RuntimeError(timeout_msg)):
            with self.WaitingQueue(self) as wq:
                msg = b"%s|%s" % (wq.message_key(), name)
                self._sendall(protocol.message(msg_type, msg))
                rx_msg = wq.get()
                if isinstance(rx_msg, RuntimeError):
                    raise rx_msg
                return rx_msg.decode()

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
            greenlet_to_objects = self._lock_counters.copy()
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
            return message, None
        return message[:pos], message[pos + 1 :]

    def _sendall(self, msg):
        with self._send_lock:
            self._socket.sendall(msg)

    def _raw_read(self):
        self.__raw_read()

    @protect_from_kill
    def __raw_read(self):
        """This listens to Beacon indefinitely (until killed or socket error).
        Closes Beacon and Redis connections when finished.
        """
        try:
            data = b""
            while True:
                with AllowKill():
                    raw_data = self._socket.recv(16 * 1024)
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
                        if self._lock_mgt(self._socket, messageType, message):
                            continue
                        elif messageType in (
                            protocol.CONFIG_GET_FILE_OK,
                            protocol.CONFIG_GET_DB_TREE_OK,
                            protocol.CONFIG_DB_FILE_RX,
                            protocol.CONFIG_GET_PYTHON_MODULE_RX,
                            protocol.CLIENT_NAME_OK,
                            protocol.WHO_LOCKED_RX,
                            protocol.LOG_SERVER_ADDRESS_OK,
                            protocol.REDIS_DATA_SERVER_OK,
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
                            protocol.WHO_LOCKED_FAILED,
                            protocol.LOG_SERVER_ADDRESS_FAIL,
                            protocol.REDIS_DATA_SERVER_FAILED,
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
                            protocol.WHO_LOCKED_END,
                        ):
                            message_key, value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None:
                                queue.put(StopIteration)
                        elif messageType == protocol.REDIS_QUERY_ANSWER:
                            host, port = message.split(b":", 1)
                            self._redis_host = host.decode()
                            self._redis_port = port.decode()
                            self._redis_query_event.set()
                        elif messageType == protocol.UDS_OK:
                            try:
                                uds_path = message.decode()
                                sock = self._uds_connect(uds_path)
                            except socket.error:
                                raise
                            else:
                                self._socket.close()
                                self._socket = sock
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
        except gevent.GreenletExit:
            pass
        except:
            sys.excepthook(*sys.exc_info())
        finally:
            with self._connect_lock:
                self._close_beacon_connection()
                self.close_all_redis_connections()

    def _close_beacon_connection(self):
        """Result of `close` of a socket error (perhaps closed)
        """
        if self._socket:
            self._socket.close()
            self._socket = None
        self._connected.clear()
        self._clean_beacon_cache()

    def _clean_beacon_cache(self):
        """Clean all cached results from Beacon queries
        """
        self._redis_host = None
        self._redis_port = None
        self._redis_data_host = None
        self._redis_data_port = None
        self._log_server_host = None
        self._log_server_port = None

    @check_connect
    def __str__(self):
        return "Connection({0}:{1})".format(self._host, self._port)
