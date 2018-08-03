# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

import gevent
from gevent.server import StreamServer, DatagramServer

from bliss.comm import tcp, udp


def tcp_echo_func(socket, address):
    while True:
        r, _, _ = gevent.select.select([socket], [], [], 3.)
        if r:
            msg = socket.recv(8192)
            if not msg:
                return
            socket.sendall(msg)


@pytest.fixture
def server_port():
    server = StreamServer(('', 0), handle=tcp_echo_func, spawn=1)
    server.family = gevent.socket.AF_INET
    server.start()
    yield server.address[1]
    server.stop()


class UdpEcho(object):
    def __call__(self, msg, add):
        self.server.sendto(msg, add)


@pytest.fixture
def udp_port():
    callback = UdpEcho()
    server = DatagramServer(('', 0), handle=callback, spawn=1)
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
def udp_socket(udp_port):
    socket = udp.Socket("127.0.0.1", udp_port)
    yield socket
    socket.close()
