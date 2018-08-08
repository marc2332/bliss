# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from gevent.server import StreamServer

from bliss.comm.tcp_proxy import Proxy

def echo(socket, address):
    # using a makefile because we want to use readline()
    rfileobj = socket.makefile(mode='rb')
    while True:
        line = rfileobj.readline()
        if not line:
            break
        if line.strip().lower() == b'quit':
            break
        socket.sendall(line)
    rfileobj.close()


@pytest.fixture
def echo_server():
    server = StreamServer(("0.0.0.0", 0), echo)
    server.start()
    yield server
    server.stop()
    server.close()


def test_proxy(beacon, echo_server):
    port = echo_server.address[1]
    client_socket = gevent.socket.socket()
    client_socket.connect(('localhost', port))
    client_socket.sendall('HELLO\n')
    assert client_socket.recv(1024) == 'HELLO\n'

    proxy = Proxy({"tcp": {"url": "socket://localhost:{}".format(port)}})
    proxy._check_connection()
    host, port = proxy._url_channel.value.split(":")

    client_socket = gevent.socket.socket()
    client_socket.connect((host, port))
    client_socket.sendall('HELLO PROXY\n')
    assert client_socket.recv(1024) == 'HELLO PROXY\n'

    proxy.close()
