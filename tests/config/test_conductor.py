# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config import static
from bliss.config.conductor import client, connection
from bliss.config import channels
import contextlib
import greenlet
import pytest
import socket
import gevent
import gc
import os


@pytest.fixture
def new_beacon_connection(ports, clean_socket):
    conn = connection.Connection("localhost", ports.beacon_port)
    yield conn
    conn.close()


def test_address_queries(new_beacon_connection):
    assert new_beacon_connection.get_redis_connection_address()
    assert new_beacon_connection.get_redis_data_server_connection_address()
    assert new_beacon_connection.get_log_server_address()


def test_redis_connections(new_beacon_connection):
    client_name = f"{socket.gethostname()}:{os.getpid()}"
    assert new_beacon_connection.get_client_name() == client_name

    getproxy = new_beacon_connection.get_redis_proxy
    getfixedproxy = new_beacon_connection.get_fixed_connection_redis_proxy

    def count_clients(proxy):
        # Only the ones from the current process. For example the tango
        # database could access Redis.
        return len(
            [client for client in proxy.client_list() if client["name"] == client_name]
        )

    proxy1 = getproxy(db=0, pool_name="pool1")
    nconnections = 1
    assert proxy1.client_getname() == client_name
    assert count_clients(proxy1) == nconnections

    new_beacon_connection.close_all_redis_connections()
    nconnections = 0
    assert proxy1.client_getname() == client_name
    nconnections += 1
    assert count_clients(proxy1) == nconnections

    proxy2 = getproxy(db=0, pool_name="pool1")
    assert proxy2.client_getname() == client_name
    assert count_clients(proxy2) == nconnections
    assert proxy1 is not proxy2
    assert proxy2 is getproxy(db=0, pool_name="pool1")

    # The Beacon connection manages Redis connection cleanup but after
    # calling `close_all_redis_connections` any existing proxy that makes
    # new connections needs to cleanup itself. This will happen on garbage
    # collection anyway but do it explicitly here so `clean_socket`
    # doesn't find sockets that have not been garbage collected yet.
    proxy1.close()
    proxy1.connection_pool.disconnect()
    nconnections -= 1
    del proxy1

    proxy3 = getfixedproxy(db=0, pool_name="pool1")
    nconnections += 1
    assert proxy3.client_getname() == client_name
    assert count_clients(proxy3) == nconnections
    assert proxy2 is not proxy3

    proxy4 = getfixedproxy(db=0, pool_name="pool1")
    nconnections += 1
    assert proxy4.client_getname() == client_name
    assert count_clients(proxy4) == nconnections
    assert proxy3 is not proxy4

    proxy5 = getproxy(db=0, pool_name="pool2")
    nconnections += 1
    assert proxy5.client_getname() == client_name
    assert count_clients(proxy5) == nconnections
    assert proxy2 is not proxy5


def test_redis_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    proxy.set("a", 0)

    def redis_comm():
        proxy = new_beacon_connection.get_redis_proxy()
        proxy.incr("a", 1)
        return proxy

    glts = [gevent.spawn(redis_comm) for _ in range(100)]
    proxies = [g.get(timeout=10) for g in glts]
    for p in proxies:
        assert p is proxies[0]
    assert proxy.get("a") == b"100"


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
    conductor_conn, conductor_proxy2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)  # could return True if successful ?
    # assert conductor_conn.lock(roby.name)
    with pytest.raises(RuntimeError):
        conductor_proxy2.lock(roby.name, timeout=0.1)
    conductor_conn.unlock(roby.name)
    conductor_proxy2.lock(roby.name)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test2"}


def test_lock_priority(beacon, two_clients):
    conductor_conn, conductor_proxy2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)  # normal priority is 50
    conductor_proxy2.lock(roby.name, priority=100)  # famous 'lock stealing'
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test2"}
    conductor_conn.lock(roby.name, priority=200)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test1"}


def test_2_clients_1_dead(beacon, two_clients):
    conductor_conn, conductor_proxy2 = two_clients
    roby = beacon.get("roby")

    conductor_conn.lock(roby.name)
    assert conductor_conn.who_locked(roby.name) == {roby.name: "test1"}
    conductor_conn.close()
    with gevent.Timeout(3):
        while conductor_proxy2.who_locked(roby.name):
            gevent.sleep(0.1)
    conductor_proxy2.lock(roby.name)
    assert conductor_proxy2.who_locked(roby.name) == {roby.name: "test2"}


def test_single_bus_for_channels(beacon):
    key = "multi_green"
    value = "hello"

    def get_channel_on_different_greenlet():
        c = channels.Channel(key, default_value=value)
        gevent.sleep(0)  # give hand to other greenlet
        return c, c.value

    chan = channels.Channel(key, default_value=value)
    chan_task = [gevent.spawn(get_channel_on_different_greenlet) for i in range(3)]

    gevent.joinall(chan_task, raise_error=True)
    assert value == chan.value
    assert all([value == t.get()[1] for t in chan_task])
    buses = set([chan._bus] + [t.get()[0]._bus for t in chan_task])
    assert len(buses) == 1
    chan._bus.close()
