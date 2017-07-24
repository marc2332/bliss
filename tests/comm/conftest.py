# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
from multiprocessing import Process, Queue
import socket
import select

def server_loop(port,rpipe):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("", 0))
    port.put(server_socket.getsockname()[-1])
    server_socket.listen(20)
    socket_list = [server_socket,rpipe]
    while True:
        r, w, e = select.select(socket_list, [], [])
        if server_socket in r:
            client_socket, addr = server_socket.accept()
            socket_list.append(client_socket)
        elif rpipe in r:
            break
        else:
            for client in r:
                data = client.recv(1024)
                if data:
                    client.sendall(data)
                else:
                    client.close()
                    socket_list.remove(client)

@pytest.fixture(scope="session")
def server_port():
    PORT = Queue()
    r,w = os.pipe()
    server_p = Process(target=server_loop,args=(PORT,w))
    server_p.start()
    os.close(w)
    yield PORT.get()
    os.close(r)
    server_p.terminate()
    server_p.join()
