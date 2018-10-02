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

import gevent
import pytest
from contextlib import contextmanager

from bliss.common import event
from bliss.comm.rpc import Server, Client


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
def rpc_server(bind="inproc://test", heartbeat=1.0):
    obj = Car("yellow", 120, turbo=True)
    server = Server(obj, stream=True, heartbeat=heartbeat)
    server.bind(bind)
    task = gevent.spawn(server.run)
    yield server, obj
    server.close()
    task.kill()


def test_api():
    url = "inproc://test"

    with rpc_server(url) as (server, car):
        client_car = Client(url)

        # class name
        assert type(client_car).__name__ == type(car).__name__ == "Car"
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
        client_car.close()


def test_event():
    url = "tcp://127.0.0.1:12345"
    results = gevent.queue.Queue()

    def callback(*args):
        results.put(args)

    with rpc_server(url) as (server, car):
        client_car = Client(url)

        event.connect(client_car, "test", callback)
        event.send(car, "test", 3)
        assert results.get() == (3,)

    with rpc_server(url) as (server, car):
        # Synchronize
        client_car.position

        event.send(car, "test", 4)
        assert results.get() == (4,)

    # close client
    client_car.close()


def test_event_with_lost_remote():
    url = "tcp://127.0.0.1:12345"
    results = gevent.queue.Queue()

    def callback(*args):
        results.put(args)

    with rpc_server(url, heartbeat=0.1) as (server, car):
        client_car = Client(url, heartbeat=0.1)

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
    client_car.close()
