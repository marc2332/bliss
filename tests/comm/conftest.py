# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import sys
import pytest
import gevent
import subprocess
from gevent.server import StreamServer, DatagramServer
from bliss.comm import tcp, udp
from bliss.common.utils import get_open_ports
from ..conftest import wait_tcp_online, wait_terminate

DELAY = 0.2


def _tcp_echo(socket, address, delay=None):
    while True:
        r, _, _ = gevent.select.select([socket], [], [], 3.)
        if r:
            msg = socket.recv(8192)
            if not msg:
                return
            if delay:
                gevent.sleep(delay)
            socket.sendall(msg)


def tcp_echo_func(socket, address):
    return _tcp_echo(socket, address)


def tcp_echo_delay_func(socket, address):
    return _tcp_echo(socket, address, delay=DELAY)


def _server_port(delay=False):
    handle = tcp_echo_delay_func if delay else tcp_echo_func
    server = StreamServer(("", 0), handle=handle, spawn=1)
    server.family = gevent.socket.AF_INET
    return server


@pytest.fixture
def server_port():
    server = _server_port()
    server.start()
    yield server.address[1]
    server.stop()


@pytest.fixture
def server_port_delay():
    server = _server_port(delay=True)
    server.start()
    yield server.address[1]
    server.stop()


class UdpEcho(object):
    def __call__(self, msg, add):
        self.server.sendto(msg, add)


@pytest.fixture
def udp_port():
    callback = UdpEcho()
    server = DatagramServer(("", 0), handle=callback, spawn=1)
    callback.server = server
    server.family = gevent.socket.AF_INET
    server.start()
    yield server.address[1]
    server.stop()


@pytest.fixture
def command(server_port):
    command = tcp.Command("127.0.0.1", server_port)
    yield command
    command.close()


@pytest.fixture
def socket(server_port):
    socket = tcp.Socket("127.0.0.1", server_port)
    yield socket
    socket.close()


@pytest.fixture
def socket_delay(server_port_delay):
    socket = tcp.Socket("127.0.0.1", server_port_delay)
    yield (socket, DELAY)
    socket.close()


@pytest.fixture
def udp_socket(udp_port):
    socket = udp.Socket("127.0.0.1", udp_port)
    yield socket
    socket.close()


@pytest.fixture
def modbus_tcp_server():
    port = get_open_ports(1)[0]
    path = os.path.dirname(__file__)
    script_path = os.path.join(path, "..", "utils", "modbus_server.py")
    p = subprocess.Popen([sys.executable, "-u", script_path, f"--port={port}"])
    wait_tcp_online("127.0.0.1", port)
    try:
        yield ("127.0.0.1", port)
    finally:
        wait_terminate(p)
