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
import sys
import socket
from socket import error as SocketError
import errno
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

@pytest.fixture(scope="module")
def echo_server(request):
    print 'in echo server fixture'
    port = request.param
    server = StreamServer(("", port), echo)
    server.start()
    yield server

@pytest.mark.parametrize('echo_server', ([12348]), indirect=True)
def test_proxy(beacon, echo_server):
    client_socket = gevent.socket.socket()
    client_socket.connect(('localhost', 12348))
    client_socket.sendall('HELLO\n')
    assert client_socket.recv(1024) == 'HELLO\n'

    proxy = Proxy({"tcp": {"url": "socket://localhost:12348"}})
    proxy._check_connection()
    host, port = proxy._url_channel.value.split(":")

    client_socket = gevent.socket.socket()
    client_socket.connect((host, port))
    client_socket.sendall('HELLO PROXY\n')
    assert client_socket.recv(1024) == 'HELLO PROXY\n'



