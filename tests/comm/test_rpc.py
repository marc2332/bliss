# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from contextlib import contextmanager
import traceback
import subprocess
import sys
import os
import numpy
import pytest

from bliss.common import event
from bliss.comm.rpc import Server, Client
from bliss.common.utils import get_open_ports

from bliss.common.logtools import get_logger

from bliss.shell.standard import debugon
from bliss.comm.exceptions import CommunicationError


def null():
    return "null"


class Car(object):
    """A silly car. This doc should show up in the client"""

    wheels = 4

    def __init__(self, color, horsepower, **kwargs):
        self.color = color
        self.horsepower = horsepower
        self.__position = 0
        self.null = null
        self.__extras = kwargs
        self.__value = 0

    @property
    def position(self):
        """this doc should show up in the client too"""
        return self.__position

    @staticmethod
    def horsepower_to_watts(horsepower):
        """so should this"""
        return horsepower * 735.499

    @staticmethod
    def watts_to_horsepower(watts):
        """so should this"""
        return watts / 735.499

    @property
    def watts(self):
        """also this one"""
        return self.horsepower_to_watts(self.horsepower)

    @watts.setter
    def watts(self, watts):
        self.horsepower = self.watts_to_horsepower(watts)

    def move(self, value, relative=False):
        """needless to say this one as well"""
        if relative:
            self.__position += value
        else:
            self.__position = value
        return self.__position

    def request_task(self, value):
        task_id = "request_task_0"
        self.__value = value
        return task_id

    def execute_task(self, task_id):
        def worker():
            gevent.sleep(1)
            event.send(self, task_id, self.__value * 2)

        gevent.spawn(worker)

    def buggy_call(self):
        """Calling this function will raise an exception"""
        raise RuntimeError("Something goes wrong")  # context not part of the exception

    def returns_exception(self):
        e = RuntimeError("foo")
        return e

    def play_music(self, data):
        pass

    def raise_timeout_exception(self):
        with gevent.Timeout(0.01):
            gevent.sleep(1)

    def __int__(self):
        return int(self.horsepower)

    def __len__(self):
        return self.wheels

    def __getitem__(self, key):
        return self.__extras[key]

    def __call__(self, *args, **kwargs):
        return self.move(*args, **kwargs)

    def __str__(self):
        return "DumbCar(color={0})".format(self.color)


@contextmanager
def rpc_server(bind="inproc://test"):
    obj = Car("yellow", 120, turbo=True)
    server = Server(obj, stream=True)
    server.bind(bind)
    task = gevent.spawn(server.run)
    yield server, obj
    server.close()
    task.kill()


def test_equality(caplog):
    url = "inproc://test"

    with rpc_server(url) as (server, car):
        client_car = Client(url)
        client_car2 = Client(url)
        debugon(client_car)
        debugon(client_car2)

        client_car._rpc_connection.connect()
        client_car2._rpc_connection.connect()

        assert {}.get(client_car) is None
        assert not client_car in (None, "bla")
        assert not "__eq__" in caplog.text
        assert not "__hash__" in caplog.text

        assert client_car != client_car2
        assert hash(client_car) != hash(client_car2)

    client_car._rpc_connection.close()
    client_car2._rpc_connection.close()


def test_api():
    url = "inproc://test"

    with rpc_server(url) as (server, car):
        client_car = Client(url)

        # class
        assert isinstance(client_car, type(car))
        # doc
        assert client_car.__doc__ == car.__doc__
        # class member
        assert client_car.wheels == car.wheels == 4
        # object member
        assert client_car.color == car.color == "yellow"
        # property
        assert client_car.position == car.position == 0

        # python protocol methods
        assert int(client_car) == int(car) == 120
        assert len(client_car) == len(car) == 4
        assert client_car["turbo"] == car["turbo"] == True
        assert str(client_car) == str(car) == "DumbCar(color=yellow)"

        # set property
        client_car.watts = 735.499 * 100
        assert client_car.watts == car.watts == 735.499 * 100

        # methods with args and kwargs
        client_car.move(11)
        assert client_car.position == car.position == 11
        client_car.move(21, relative=True)
        assert client_car.position == car.position == 32

    # close client
    client_car._rpc_connection.close()


def test_logging(caplog):
    url = "inproc://test"

    with rpc_server(url) as (server, car):
        client_car = Client(url)
        debugon(client_car)

        logger = get_logger(client_car)
        assert logger

        client_car.move(11)

    assert "rpc client (inproc://test): 'call' args=['move', 11]" in caplog.text

    # close client
    client_car._rpc_connection.close()


def test_exceptions():
    url = "inproc://test"

    with rpc_server(url) as (server, car):
        client_car = Client(url)

        try:
            client_car.buggy_call()
        except RuntimeError as e:
            tb = traceback.format_tb(e.__traceback__)
            assert "test_rpc" in tb[-1]
            assert "buggy_call" in tb[-1]
            assert "# context not part of the exception" in tb[-1]
        else:
            assert False

        e2 = client_car.returns_exception()
        assert isinstance(e2, RuntimeError)
        assert e2.args[0] == "foo"

    # close client
    client_car._rpc_connection.close()


def test_wrong_api():
    url = "inproc://test"

    with rpc_server(url) as (server, car):
        client_car = Client(url)

        with pytest.raises(AttributeError, match="unexisting_method"):
            client_car.unexisting_method()

    # close client
    client_car._rpc_connection.close()


def test_event():

    url = "tcp://127.0.0.1:12345"
    results = gevent.queue.Queue()

    def callback(*args):
        results.put(args)

    with rpc_server(url) as (server, car):
        client_car = Client(url)
        client_car._rpc_connection.connect()

        event.connect(client_car, "test", callback)
        event.send(car, "test", 3)
        assert results.get() == (3,)

    with rpc_server(url) as (server, car):
        # Synchronize
        client_car.position

        event.send(car, "test", 4)
        assert results.get() == (4,)

    # close client
    client_car._rpc_connection.close()


def test_remote_task():

    url = "tcp://127.0.0.1:12345"
    results = gevent.queue.Queue()

    def callback(*args):
        results.put(args)

    with rpc_server(url) as (server, car):
        client_car = Client(url)
        client_car._rpc_connection.connect()

        task_id = car.request_task(3)
        event.connect(client_car, task_id, callback)
        car.execute_task(task_id)
        assert results.get() == (6,)

    # close client
    client_car._rpc_connection.close()


def test_event_with_lost_remote():

    url = "tcp://127.0.0.1:12345"
    results = gevent.queue.Queue()

    def callback(*args):
        results.put(args)

    with rpc_server(url) as (server, car):
        client_car = Client(url)
        client_car._rpc_connection.connect()

        event.connect(client_car, "test", callback)
        event.send(car, "test", 3)
        assert results.get() == (3,)

    gevent.sleep(0.4)

    with rpc_server(url) as (server, car):
        # Synchronize
        client_car.position

        event.send(car, "test", 4)
        assert results.get() == (4,)

    # close client
    client_car._rpc_connection.close()


def test_issue_1944(beacon):
    url = f"tcp://127.0.0.1:{get_open_ports(1)[0]}"

    script = subprocess.Popen(
        [
            sys.executable,
            "-u",
            os.path.join(os.path.dirname(__file__), "issue_1944_server.py"),
            url,
        ],
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )

    ### synchronize with process start
    with gevent.Timeout(5):
        out = script.stdout.readline()
        assert out == "OK\n"
    gevent.sleep(1)
    ###

    client_obj = Client(url)
    try:
        # the next line reproduces the problem in issue #1944
        names = client_obj.set_root_node(beacon._root_node)
        # the next line is just the check that the above call worked
        assert beacon.names_list == names
    finally:
        script.terminate()
        client_obj._rpc_connection.close()


def test_client_collision(beacon):
    """
    Create a RPC client-server and try to interleave 2 client requests
    """
    url = "tcp://127.0.0.1:12345"

    def monitor_car(car):
        """Request many little things"""
        for _ in range(10):
            car.position
            gevent.sleep(0.01)

    def play_music(car, data):
        """Request a huge big thing"""
        car.play_music(data)

    data = numpy.empty((1024 * 1024 * 40), dtype=numpy.uint8)

    with rpc_server(url):
        client_car = Client(url)
        client_car._rpc_connection.connect()

        g1 = gevent.spawn(monitor_car, client_car)
        g2 = gevent.spawn(play_music, client_car, data)

        gevent.joinall([g1, g2])

    gevent.sleep(0.4)
    client_car._rpc_connection.close()


def test_timeout_exception(beacon):
    url = "tcp://127.0.0.1:12345"

    with rpc_server(url):
        client_car = Client(url)

        with pytest.raises(gevent.Timeout):
            client_car.raise_timeout_exception()

    client_car._rpc_connection.close()


def test_disconnect_callback(beacon):
    url = "tcp://127.0.0.1:12345"
    disconnected = False

    def server_disconnected():
        nonlocal disconnected
        disconnected = True

    with rpc_server(url):
        client_car = Client(url, disconnect_callback=server_disconnected)
        client_car._rpc_connection.connect()

    gevent.sleep(1)
    assert disconnected

    disconnected = False
    with rpc_server(url):
        client_car = Client(url, disconnect_callback=server_disconnected)
        client_car._rpc_connection.connect()
        client_car._rpc_connection.close()

    gevent.sleep(1)
    assert not disconnected


def test_nonexisting_host(beacon):
    url = "tcp://wid666:12345"

    with rpc_server(url):
        client = Client(url)

        with pytest.raises(CommunicationError):
            try:
                client.connect()
            except Exception as eee:
                assert "wid666" in str(eee)
                assert "12345" in str(eee)
                raise CommunicationError(str(eee)) from eee

    client._rpc_connection.close()


def test_disconnect_event_with_closed_server():

    url = "tcp://127.0.0.1:12345"
    results = gevent.queue.Queue()

    def callback(*args):
        results.put(args)

    with rpc_server(url) as (server, car):
        client_car = Client(url)
        client_car._rpc_connection.connect()

        event.connect(client_car, "test", callback)
        event.send(car, "test", 3)
        assert results.get() == (3,)

    gevent.sleep(0.4)
    event.disconnect(client_car, "test", callback)

    with rpc_server(url) as (server, car):
        # Synchronize
        client_car.position

        event.send(car, "test", 4)
        # the previous event should not update 'results' since
        # the event is disconnected
        assert len(results) == 0

    # close client
    client_car._rpc_connection.close()
