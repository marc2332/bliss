# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import unittest
import time
import socket
import gevent
import sys
import os
from multiprocessing import Process, Queue
import select

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.path.pardir, os.path.pardir)))

from bliss.comm import tcp

PORT = Queue()


def server_loop():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("", 0))
    PORT.put(server_socket.getsockname()[-1])
    server_socket.listen(20)
    socket_list = [server_socket]
    while True:
        r, w, e = select.select(socket_list, [], [])
        if server_socket in r:
            client_socket, addr = server_socket.accept()
            socket_list.append(client_socket)
        else:
            for client in r:
                data = client.recv(1024)
                if data:
                    client.sendall(data)
                else:
                    client.close()
                    socket_list.remove(client)

server_p = Process(target=server_loop)
server_p.start()

SERVER_PORT = PORT.get()


class TestTcpComm(unittest.TestCase):

    def setUp(self):
        self.server_socket_port = SERVER_PORT

    def test_connect(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        self.assertTrue(s.connect())

    def test_write_read_n_bytes(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        data = s.write_read("A" * 1024, size=1024)
        self.assertEqual(len(data), 1024)

    def test_write_readline(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        msg = "HELLO\nWORLD\n"
        transaction = s._write(msg)
        self.assertEqual(
            s._readline(
                transaction,
                clear_transaction=False),
            "HELLO")
        self.assertEqual(s._readline(transaction), "WORLD")

    def test_write_readline2(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        self.assertEqual(s.write_readline("HELLO\n"), "HELLO")
        self.assertEqual(s.write_readline("WORLD\n"), "WORLD")

    def test_write_readlines(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        self.assertEqual(
            s.write_readlines(
                "HELLO\nWORLD\n", 2), [
                "HELLO", "WORLD"])

    def test_readline_timeout(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        t0 = time.time()
        transaction = s.new_transaction()
        try:
            s._readline(transaction, timeout=1)
        except RuntimeError:
            t = time.time() - t0
            self.assertTrue(t - 1 < 0.1)

    def test_tryconnect(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        s.connect()
        s.close()
        self.assertEqual(s.write_read("X"), "X")

    def test_concurency(self):
        s = tcp.Command("127.0.0.1", self.server_socket_port)
        s.connect()

        def task_function(msg, i):
            self.assertEqual(s.write_readline(msg + '\n'), msg)

        def task_with_exception(msg, i):
            msg += '_exception'
            try:
                transaction = s._write(msg)
                s._readline(transaction, timeout=0.01, eol='\r',
                            clear_transaction=False)
            except RuntimeError:  # timeout
                rxmsg = s._read(transaction, size=len(msg))
                self.assertEqual(rxmsg, msg)

        tasks = []
        for i, msg in enumerate(['HELLO', 'WORLD', 'HOUPPI',
                                 'tagada', 'super', 'mario',
                                 'ludgi']):
            tasks.append(gevent.spawn(task_function, msg, i))
            if i % 2:
                tasks.append(gevent.spawn(task_with_exception, msg, i))

        for t in tasks:
            t.join(3)

    def test_connect_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        self.assertTrue(s.connect())

    def test_write_read_n_bytes_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        data = s.write_read("A" * 1024, size=1024)
        self.assertEqual(len(data), 1024)

    def test_write_readline_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        msg = "HELLO\nWORLD\n"
        s.write(msg)
        self.assertEqual(s.readline(), "HELLO")
        self.assertEqual(s.readline(), "WORLD")

    def test_write_readline2_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        self.assertEqual(s.write_readline("HELLO\n"), "HELLO")
        self.assertEqual(s.write_readline("WORLD\n"), "WORLD")

    def test_write_readlines_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        self.assertEqual(
            s.write_readlines(
                "HELLO\nWORLD\n", 2), [
                "HELLO", "WORLD"])

    def test_readline_timeout_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        t0 = time.time()
        try:
            s.readline(timeout=1)
        except RuntimeError:
            t = time.time() - t0
            self.assertTrue(t - 1 < 0.1)

    def test_tryconnect_socket(self):
        s = tcp.Socket("127.0.0.1", self.server_socket_port)
        s.connect()
        s.close()
        self.assertEqual(s.write_read("X"), "X")

    @classmethod
    def tearDownClass(cls):
        server_p.terminate()

if __name__ == '__main__':
    unittest.main()
