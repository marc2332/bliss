# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
from gevent.server import StreamServer, DatagramServer
from gevent import select, socket

def tcp_echo_func(socket,address):
    while True:
        r,_,_ = select.select([socket],[],[],3.)
        if r:
            msg = socket.recv(8192)
            if not msg:
                return
            socket.sendall(msg)

@pytest.fixture(scope="session")
def server_port():
    server = StreamServer(('',0),handle=tcp_echo_func)
    server.family = socket.AF_INET
    server.start()
    yield server.address[1]
    server.stop()

class UdpEcho(object):
    def __call__(self,msg,add):
        self.server.sendto(msg,add)

@pytest.fixture(scope="session")
def udp_port():
    callback = UdpEcho()
    server = DatagramServer(('',0),handle=callback)
    callback.server = server
    server.family = socket.AF_INET
    server.start()
    yield server.address[1]
    server.stop()
