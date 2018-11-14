# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import os, sys

import errno
import gevent
from gevent import socket, select, event

from bliss.comm.tcp import Tcp
from bliss.config.conductor.client import Lock
from bliss.config.channels import Channel


def _wait_pid(read_pipe, pid):
    while True:
        r, _, _ = select.select([read_pipe], [], [])
        if r:
            out = os.read(read_pipe, 8192)
            if not out:
                os.waitpid(pid, 0)
                break


class Proxy(object):
    TCP = 0

    def __init__(self, config):
        if "tcp" in config:
            tcp_config = config.get("tcp")
            if hasattr(config, "deep_copy"):
                self._config = tcp_config.deep_copy()
            else:
                self._config = tcp_config.copy()
            self._mode = self.TCP
            cnx = Tcp(**tcp_config)
            self.name = "%s:%d" % (cnx._host, cnx._port)
        else:
            raise NotImplemented("Proxy: Not managed yet")

        self._cnx = None
        self._join_task = None
        self._url_channel = Channel("proxy:%s" % self.name)

    def kill_proxy_server(self):
        self._url_channel.value = None

    def close(self):
        self.kill_proxy_server()
        if self._join_task is not None:
            self._join_task.join()
        self._join_task = None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        was_connected = None
        if not name.startswith("_"):
            was_connected = self._check_connection()

        attr = getattr(self._cnx, name)
        if callable(attr) and was_connected is False:

            def wrapper_func(*args, **kwargs):
                try:
                    return attr(*args, **kwargs)
                except socket.error as e:
                    if e.errno == errno.EPIPE:
                        raise socket.error(errno.ECONNREFUSED, "Connection refused")
                else:
                    raise

            return wrapper_func
        return attr

    def _check_connection(self):
        if self._mode == self.TCP:
            if self._cnx is None or not self._cnx._connected:
                if hasattr(self._config, "deep_copy"):
                    local_cfg = self._config.deep_copy()
                else:
                    local_cfg = self._config.copy()
                url = local_cfg.pop("url")
                cnx = Tcp(url, **local_cfg)
                host, port = cnx._host, cnx._port
                proxy_url = self._fork_server(host, port)
                self._cnx = Tcp(proxy_url, **local_cfg)
                return False

    def _fork_server(self, host, port):
        with Lock(self):
            sync = event.Event()

            def port_cbk(proxy_url):
                if not proxy_url:
                    # filter default value
                    return
                sync.set()

            try:
                self._url_channel.register_callback(port_cbk)
                local_url = self._url_channel.value
                if local_url is None:
                    self._join_task = self._real_server_fork(host, port)
                    gevent.sleep(0)
                    sync.wait()
                    local_url = self._url_channel.value
                return local_url
            finally:
                self._url_channel.unregister_callback(port_cbk)

    def _real_server_fork(self, host, port):
        script_name = __file__
        read, write = os.pipe()
        pid = os.fork()
        if pid == 0:  # child
            os.dup2(write, sys.stdout.fileno())
            os.dup2(write, sys.stderr.fileno())
            os.closerange(3, write + 1)
            os.execl(
                sys.executable,
                sys.executable,
                __file__,
                "--channel-name",
                self._url_channel.name,
                "--port",
                str(port),
                "--host",
                host,
            )
            sys.exit(0)
        else:
            os.close(write)
            wait_greenlet = gevent.spawn(_wait_pid, read, pid)
            wait_greenlet.start()
            return wait_greenlet


def main():  # proxy server part
    import signal, os

    global pipe_write
    pipe_read, pipe_write = os.pipe()

    def _stop_server(*args):
        # import os
        os.close(pipe_write)

    signal.signal(signal.SIGINT, _stop_server)
    signal.signal(signal.SIGTERM, _stop_server)

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--channel-name",
        dest="channel_name",
        default=None,
        help="channel where proxy url is stored",
    )
    parser.add_argument("--host", dest="host", help="destination host")
    parser.add_argument("--port", dest="port", type=int, help="destination port")

    _options = parser.parse_args()

    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(("", 0))
    tcp.listen(16)
    proxy_port = tcp.getsockname()[1]
    proxy_host = socket.gethostname()

    server_url = "%s:%d" % (proxy_host, proxy_port)

    global dont_reset_channel
    dont_reset_channel = False

    def channel_cbk(value):
        global dont_reset_channel
        if value != server_url:
            dont_reset_channel = True
            try:
                os.close(pipe_write)
            except OSError:
                pass

    channel_name = _options.channel_name or "proxy:%s:%d" % (
        _options.host,
        _options.port,
    )
    channel = Channel(channel_name, value=server_url, callback=channel_cbk)

    runFlag = True
    fd_list = [tcp, pipe_read]
    global client
    global dest
    client = None
    dest = None
    try:
        while runFlag:
            rlist, _, _ = select.select(fd_list, [], [])
            for s in rlist:
                if s == tcp:
                    accept_flag = True
                    try:
                        if dest is None:
                            dest = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            dest.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                            dest.connect((_options.host, _options.port))
                            fd_list.append(dest)
                    except:
                        dest = None
                        accept_flag = False

                    if client is not None:
                        fd_list.remove(client)
                        client.close()
                        client = None

                    client, addr = tcp.accept()
                    if accept_flag:
                        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        fd_list.append(client)
                    else:
                        client.close()
                        client = None

                elif s == client:
                    try:
                        raw_data = client.recv(16 * 1024)
                    except:
                        raw_data = None

                    if raw_data:
                        dest.sendall(raw_data)
                    else:
                        fd_list.remove(client)
                        client.close()
                        client = None
                elif s == dest:
                    try:
                        raw_data = dest.recv(16 * 1024)
                    except:
                        raw_data = None

                    if raw_data:
                        client.sendall(raw_data)
                    else:
                        dest.close()
                        fd_list.remove(dest)
                        dest = None
                        fd_list.remove(client)
                        client.close()
                        client = None
                elif s == pipe_read:
                    runFlag = False
                    break
    finally:
        if dont_reset_channel is False:
            channel.value = None
            gevent.sleep(0)


if __name__ == "__main__":
    main()
