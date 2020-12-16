# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import os
import time
import argparse
import weakref
import gevent
import gevent.event

from bliss.config import settings, static
from bliss.comm import rpc
from bliss.common import protocols
from bliss.common import counter, logtools
from . import plugins

_Port2Object = weakref.WeakValueDictionary()


class ConnectionError(RuntimeError):
    pass


def get_object_from_port(port):
    return _Port2Object.get(port)


# --- CLIENT ---
class Client(protocols.CounterContainer):
    def __init__(self, name, config_node):
        self.__name = name
        self._config_node = config_node
        self._proxy = None
        self._connexion_info = settings.Struct(f"service:{name}")
        try:
            self.connect()
        except:
            logtools.log_warning(self, "Service %s not running", name)

    def __dir__(self):
        attributes = ["close", "connect", "config", "__info__"]
        try:
            self.connect()
        except ConnectionError:
            pass
        else:
            try:
                attr_proxy = dir(self._proxy)
            except ConnectionRefusedError:
                pass
            else:
                attributes.extend(attr_proxy)
        return attributes

    def __getattr__(self, name):
        try:
            self.connect()
        except ConnectionError:
            raise AttributeError(name)

        return getattr(self._proxy, name)

    def __setattr__(self, name, value):
        if name.startswith("_Client") or name in (
            "_proxy",
            "_config_node",
            "_connexion_info",
        ):
            return super().__setattr__(name, value)

        self.connect()
        return setattr(self._proxy, name, value)

    def __info__(self):
        info = self._connexion_info
        pid = info.pid
        hostname = info.hostname
        if not pid:
            pid_info = "**Not Started**"
            if hostname:
                pid_info = pid_info + f" (previously Running on host **{hostname}**)"
        else:
            pid_info = f"with pid {pid}"
        info_str = f"Service {self.__name} on host {hostname}:{info.port} {pid_info}"
        try:
            self.connect()
        except ConnectionError:
            pass
        if self._proxy is not None:
            try:
                extra_info = self._proxy.__info__()
            except:
                pass
            else:
                info_str += "\n\n" + extra_info
        return info_str

    @property
    def config(self):
        return self._config_node

    def close(self):
        try:
            if self._proxy:
                self._proxy.close()
        finally:
            self._proxy = None

    def connect(self):
        if self._proxy is None:
            hostname = self._connexion_info.hostname
            port = self._connexion_info.port
            if hostname is None or port is None:
                raise ConnectionError(
                    f"Server service **{self.__name}** has never been started"
                )

            pid = self._connexion_info.pid
            if not pid:
                raise ConnectionError(
                    f"Server service **{self.__name}** is Down, "
                    f"previously started on **{hostname}**"
                )

            client = rpc.Client(
                f"tcp://{hostname}:{port}", disconnect_callback=self.close
            )

            self._proxy = plugins.get_local_client(client, port, self.config)

    @property
    def counters(self):
        self.connect()
        if isinstance(self._proxy, protocols.CounterContainer):
            return self._proxy.counters
        if isinstance(self._proxy, counter.Counter):
            return protocols.counter_namespace([self._proxy])
        return protocols.counter_namespace([])


# --- SERVER ---
def _set_info(info, port):
    if info is not None:
        info._proxy.ttl(None)
        info.hostname = gevent.socket.gethostname()
        info.port = port
        info.pid = os.getpid()
        info.started = time.time()


def _start_server(obj, name, info, services, server_loop, obj_to_server):
    server = rpc.Server(obj)
    server.bind("tcp://localhost:0")
    port = server._socket.getsockname()[1]
    if name is not None:
        services[name] = info, server
    obj_to_server[obj] = info, server
    _set_info(info, port)
    _Port2Object[port] = obj
    server_ready_event = gevent.event.Event()
    server_loop.append(gevent.spawn(server.run, server_ready_event))
    server_ready_event.wait()
    print(f"Starting service {name} for object {obj} at port {port}")
    return port


def main():
    """
    Server service
    """
    # Argument parsing
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="+", help="named objects to export as a service")
    args = parser.parse_args()
    config = static.get_config()
    services = dict()
    server_loop = list()
    obj_to_server = dict()

    def start_sub_server(obj):
        _, server = obj_to_server.get(obj, (None, None))
        if server is None:
            port = _start_server(obj, None, None, services, server_loop, obj_to_server)
        else:
            port = server._socket.getsockname()[1]
        return port

    def _start_service(name):
        info = settings.Struct(f"service:{name}")
        obj = config._get(name, direct_access=True)
        if obj in obj_to_server:
            prev_info, server = obj_to_server[obj]
            if prev_info is None:
                _set_info(info, server._socket.getsockname()[1])
                obj_to_server[obj] = info, server
                services[name] = info, server
            return obj

        obj = plugins.get_local_server(obj, start_sub_server)
        _start_server(obj, name, info, services, server_loop, obj_to_server)
        return obj

    # Patch config get to start a service on any dependencies.
    config.get = _start_service
    try:
        for name in set(args.name):
            # check that is defined as a service
            config_node = config.get_config(name)
            if config_node is None:
                raise ValueError(
                    f"Can't get object named **{name}**, not in configuration"
                )
            if not config_node.is_service:
                raise ValueError(f"object **{name}** is not defined as a service")

            _start_service(name)

        try:
            gevent.wait()
        except KeyboardInterrupt:
            gevent.killall(server_loop)
    finally:
        for info, server in services.values():
            try:
                server.close()
            except:
                pass
            # Set redis key to a time to live of 2 months
            # Just to clean it in case it's no more used.
            if info is not None:
                info._proxy.ttl(2 * 30 * 24 * 3600)
                info.pid = 0
