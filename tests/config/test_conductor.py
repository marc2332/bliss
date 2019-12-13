# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import static
from bliss.config.conductor import client, connection
import contextlib
import greenlet
import pytest
import socket
import gevent
import gc
import os


@pytest.fixture
def two_clients(beacon):
    conductor_conn = client.get_default_connection()
    conductor_conn.set_client_name("test1")
    client._default_connection = None  # force making a new connection
    conductor_conn2 = client.get_default_connection()
    conductor_conn2.set_client_name("test2")
    yield conductor_conn, conductor_conn2
    conductor_conn.close()
    conductor_conn2.close()


def test_client_name(beacon):
    conductor_conn = client.get_default_connection()

    conductor_conn.set_client_name("test")

    assert conductor_conn.get_client_name() == "test"


def test_lock(beacon):
    roby = beacon.get("roby")
    conductor_conn = client.get_default_connection()

    try:
        client.lock(roby)
        lock_owner = conductor_conn.who_locked(
            roby.name
        )  # why not client.who_locked(roby) ?
        assert lock_owner == {roby.name: f"{socket.gethostname()}:{os.getpid()}"}
    finally:
        client.unlock(roby)
    assert not conductor_conn.who_locked(roby.name)


def test_who_locked_client_name(beacon):
    roby = beacon.get("roby")
    conductor_conn = client.get_default_connection()
    conductor_conn.set_client_name("test")

    try:
        client.lock(roby)
        lock_owner = conductor_conn.who_locked(roby.name)
        assert lock_owner == {roby.name: "test"}
    finally:
        client.unlock(roby)
    assert not conductor_conn.who_locked(roby.name)


def test_2_clients_lock(beacon, two_clients):
    conductor_conn, conductor_conn2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)  # could return True if successful ?
    # assert conductor_conn.lock(roby.name)
    with pytest.raises(RuntimeError):
        conductor_conn2.lock(roby.name, timeout=0.1)
    conductor_conn.unlock(roby.name)
    conductor_conn2.lock(roby.name)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test2"}


def test_lock_priority(beacon, two_clients):
    conductor_conn, conductor_conn2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)  # normal priority is 50
    conductor_conn2.lock(roby.name, priority=100)  # famous 'lock stealing'
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test2"}
    conductor_conn.lock(roby.name, priority=200)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test1"}


def test_2_clients_1_dead(beacon, two_clients):
    conductor_conn, conductor_conn2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test1"}
    conductor_conn.close()
    assert not conductor_conn2.who_locked(roby.name)
    conductor_conn2.lock(roby.name)
    assert conductor_conn2.who_locked(roby.name) == {roby.name: "test2"}

@contextlib.contextmanager
def new_conductor_conn(port):
    conductor_conn = connection.Connection("localhost", port)
    yield conductor_conn
    conductor_conn.close()

def test_multiple_greenlets(ports):
    # make a new connection to Beacon, so it is not already connected
    with new_conductor_conn(ports.beacon_port) as conductor_conn:
        def get_redis_conn():
            # retrieve redis connection from Beacon:
            # this will call 'connect' concurrently
            redis_conn = conductor_conn.get_redis_connection()

            redis_keys = redis_conn.keys("*")

            return redis_conn, redis_keys

        # start 2 greenlets
        g1 = gevent.spawn(get_redis_conn)
        g2 = gevent.spawn(get_redis_conn)

        redis_conn1, keys1 = g1.get()
        redis_conn2, keys2 = g2.get()

        assert redis_conn1 is redis_conn2

        assert len(conductor_conn._redis_connection) == 1

