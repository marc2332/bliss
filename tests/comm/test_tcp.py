# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import pytest
import gevent
from bliss.comm import tcp


def test_connect(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    assert s.connect() == True

def test_write_read_n_bytes(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    data = s.write_read("A" * 1024, size=1024)
    assert len(data) == 1024

def test_write_readline(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    msg = "HELLO\nWORLD\n"
    transaction = s._write(msg)
    assert s._readline(transaction,clear_transaction=False) == "HELLO"
    assert s._readline(transaction) == "WORLD"

def test_write_readline2(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    assert s.write_readline("HELLO\n") == "HELLO"
    assert s.write_readline("WORLD\n") == "WORLD"

def test_write_readlines(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    assert s.write_readlines("HELLO\nWORLD\n", 2) == ["HELLO", "WORLD"]

def test_readline_timeout(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    t0 = time.time()
    transaction = s.new_transaction()
    try:
        s._readline(transaction, timeout=1)
    except RuntimeError:
        t = time.time() - t0
        assert t - 1 < 0.1

def test_tryconnect(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    assert s.write_read("X") == "X"

def test_concurency(server_port):
    s = tcp.Command("127.0.0.1", server_port)
    s.connect()

    def task_function(msg, i):
        assert s.write_readline(msg + '\n') == msg

    def task_with_exception(msg, i):
        msg += '_exception'
        try:
            transaction = s._write(msg)
            s._readline(transaction, timeout=0.01, eol='\r',
                        clear_transaction=False)
        except RuntimeError:  # timeout
            rxmsg = s._read(transaction, size=len(msg))
            assert rxmsg == msg

    tasks = []
    for i, msg in enumerate(['HELLO', 'WORLD', 'HOUPPI',
                             'tagada', 'super', 'mario',
                             'ludgi']):
        tasks.append(gevent.spawn(task_function, msg, i))
        if i % 2:
            tasks.append(gevent.spawn(task_with_exception, msg, i))

    for t in tasks:
        t.join(3)

def test_connect_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    assert s.connect() == True

def test_write_read_n_bytes_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    data = s.write_read("A" * 1024, size=1024)
    assert len(data) == 1024

def test_write_readline_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    msg = "HELLO\nWORLD\n"
    s.write(msg)
    assert s.readline() == "HELLO"
    assert s.readline() == "WORLD"

def test_write_readline2_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    assert s.write_readline("HELLO\n") == "HELLO"
    assert s.write_readline("WORLD\n") == "WORLD"

def test_write_readlines_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    assert s.write_readlines("HELLO\nWORLD\n", 2) == ["HELLO", "WORLD"]

def test_readline_timeout_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    t0 = time.time()
    try:
        s.readline(timeout=1)
    except RuntimeError:
        t = time.time() - t0
        assert t - 1 < 0.1

def test_tryconnect_socket(server_port):
    s = tcp.Socket("127.0.0.1", server_port)
    s.connect()
    s.close()
    assert s.write_read("X") == "X"
