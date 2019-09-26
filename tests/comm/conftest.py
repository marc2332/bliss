# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from collections import defaultdict
from socketserver import TCPServer
import threading

import pytest

import gevent
from gevent.server import StreamServer, DatagramServer

from umodbus import conf
from umodbus.server.tcp import RequestHandler, get_server
from umodbus.utils import log_to_stream


from bliss.comm import tcp, udp
from tests.conftest import get_open_ports


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
    address = ("127.0.0.1", *get_open_ports(1))

    t = threading.Thread(target=modbus_server, args=(address,))
    t.start()
    yield address
    t.do_run = False
    t.join(1)


def modbus_server(address):
    """
    Creates a synchronous modbus server serving 2 different memory areas
     * coils and inputs for boolean values
     * registers and holding for non boolean values

    Supported modbus functions are:
      * 1,2,3,4,5,6,15,16
    """
    regs_boolean = defaultdict(bool)  # modbus coils and inputs share the same area
    regs_boolean_size = 100
    regs_word = defaultdict(
        int
    )  # modbus input registers and holding registers shares the same area
    regs_word_size = 100

    # Enable values to be signed (default is False).
    conf.SIGNED_VALUES = True

    TCPServer.allow_reuse_address = True
    TCPServer.timeout = .1
    app = get_server(TCPServer, address, RequestHandler)

    # 1 read coil, 2 read discrete input
    @app.route(
        slave_ids=[1],
        function_codes=[1, 2],
        addresses=list(range(0, regs_boolean_size)),
    )
    def read_coils(slave_id, function_code, address):
        return regs_boolean[address]

    # 5 write coil, 15 write multiple coils
    @app.route(
        slave_ids=[1],
        function_codes=[5, 15],
        addresses=list(range(0, regs_boolean_size)),
    )
    def write_coils(slave_id, function_code, address, value):
        regs_boolean[address] = value

    # 3 read holding registers, 4 read input registers
    @app.route(
        slave_ids=[1], function_codes=[3, 4], addresses=list(range(0, regs_word_size))
    )
    def read_words(slave_id, function_code, address):
        return regs_word[address]

    @app.route(
        slave_ids=[1], function_codes=[6, 16], addresses=list(range(0, regs_word_size))
    )
    def write_words(slave_id, function_code, address, value):
        regs_word[address] = value

    t = threading.currentThread()

    try:
        while getattr(t, "do_run", True):  # handles until a signal from parent thread
            app.handle_request()
    finally:
        app.server_close()
