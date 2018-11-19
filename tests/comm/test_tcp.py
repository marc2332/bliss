# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import pytest
import gevent
from bliss.common.event import connect, disconnect


def test_connect(command):
    assert command.connect() is True


def test_write_read_n_bytes(command):
    data = command.write_read("A" * 1024, size=1024)
    assert len(data) == 1024


def test_write_readline(command):
    msg = "HELLO\nWORLD\n"
    transaction = command._write(msg)
    assert command._readline(transaction, clear_transaction=False) == "HELLO"
    assert command._readline(transaction) == "WORLD"


def test_write_readline2(command):
    assert command.write_readline("HELLO\n") == "HELLO"
    assert command.write_readline("WORLD\n") == "WORLD"


def test_write_readlines(command):
    assert command.write_readlines("HELLO\nWORLD\n", 2) == ["HELLO", "WORLD"]


def test_readline_timeout(command):
    t0 = time.time()
    transaction = command.new_transaction()
    try:
        command._readline(transaction, timeout=1)
    except RuntimeError:
        t = time.time() - t0
        assert t - 1 < 0.1


def test_tryconnect(command):
    assert command.write_read("X") == "X"


def test_concurency(command):
    command.connect()

    def task_function(msg, i):
        assert command.write_readline(msg + "\n") == msg

    def task_with_exception(msg, i):
        msg += "_exception"
        try:
            transaction = command._write(msg)
            command._readline(
                transaction, timeout=0.01, eol="\r", clear_transaction=False
            )
        except RuntimeError:  # timeout
            rxmsg = command._read(transaction, size=len(msg))
            assert rxmsg == msg

    tasks = []
    for i, msg in enumerate(
        ["HELLO", "WORLD", "HOUPPI", "tagada", "super", "mario", "ludgi"]
    ):
        tasks.append(gevent.spawn(task_function, msg, i))
        if i % 2:
            tasks.append(gevent.spawn(task_with_exception, msg, i))

    for t in tasks:
        t.join(3)


def test_connect_socket(socket):
    assert socket.connect() is True


def test_write_read_n_bytes_socket(socket):
    data = socket.write_read("A" * 1024, size=1024)
    assert len(data) == 1024


def test_write_readline_socket(socket):
    msg = "HELLO\nWORLD\n"
    socket.write(msg)
    assert socket.readline() == "HELLO"
    assert socket.readline() == "WORLD"


def test_write_readline2_socket(socket):
    assert socket.write_readline("HELLO\n") == "HELLO"
    assert socket.write_readline("WORLD\n") == "WORLD"


def test_write_readlines_socket(socket):
    assert socket.write_readlines("HELLO\nWORLD\n", 2) == ["HELLO", "WORLD"]


def test_readline_timeout_socket(socket):
    t0 = time.time()
    try:
        socket.readline(timeout=1)
    except RuntimeError:
        t = time.time() - t0
        assert t - 1 < 0.1


def test_tryconnect_socket(socket):
    socket.connect()
    socket.close()
    assert socket.write_read("X") == "X"


def test_external_timeout(socket_delay):
    socket, delay = socket_delay
    socket.connect()
    start_time = time.time()
    with gevent.Timeout(0.1):
        assert socket.write_read("X") == "X"
    end_time = time.time()
    assert start_time + delay == pytest.approx(end_time)

    start_time = time.time()
    with gevent.Timeout(0.1):
        assert socket.write_readline("X\n") == "X"
    end_time = time.time()
    assert start_time + delay == pytest.approx(end_time)
    assert socket._connected


def test_external_runtimeerror(socket_delay):
    socket, delay = socket_delay
    socket.connect()
    start_time = time.time()
    with pytest.raises(RuntimeError):
        with gevent.Timeout(0.1, RuntimeError("should quit")):
            assert socket.write_read("Y") != "Y"
    end_time = time.time()
    assert start_time + 0.1 == pytest.approx(end_time)
    assert not socket._connected


def test_connection_socket_event(socket):
    test_connect = dict()

    def connection_cbk(value):
        test_connect["connected"] = value

    connect(socket, "connect", connection_cbk)
    try:
        socket.connect()
        assert test_connect.get("connected")
        socket.close()
        assert test_connect.get("connected") == False
    finally:
        disconnect(socket, "connect", connection_cbk)


def test_connection_command_event(command):
    test_connect = dict()

    def connection_cbk(value):
        test_connect["connected"] = value

    connect(command, "connect", connection_cbk)
    try:
        command.connect()
        assert test_connect.get("connected")
        command.close()
        assert test_connect.get("connected") == False
    finally:
        disconnect(command, "connect", connection_cbk)
