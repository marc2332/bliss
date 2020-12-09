# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import contextlib
import gevent
import greenlet
import socket
import pytest

from bliss.config.conductor import client, connection
from bliss.config.conductor.redis_caching import RedisCacheError
from bliss.config import channels


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

    def count_clients(proxy):
        # Only the ones from the current process. For example the tango
        # database could access Redis.
        return len(
            [client for client in proxy.client_list() if client["name"] == client_name]
        )

    proxy1 = new_beacon_connection.get_redis_proxy(db=0)
    nconnections = 1
    assert proxy1.client_getname() == client_name
    assert count_clients(proxy1) == nconnections

    new_beacon_connection.close_all_redis_connections()
    nconnections = 0
    assert proxy1.client_getname() == client_name
    nconnections += 1
    assert count_clients(proxy1) == nconnections

    proxy2 = new_beacon_connection.get_redis_proxy(db=0)
    assert proxy2.client_getname() == client_name
    assert count_clients(proxy2) == nconnections
    assert proxy1 is not proxy2
    assert proxy2 is new_beacon_connection.get_redis_proxy(db=0)

    # The Beacon connection manages Redis connection cleanup but after
    # calling `close_all_redis_connections` any existing proxy that makes
    # new connections needs to cleanup itself. This will happen on garbage
    # collection anyway but do it explicitly here so `clean_socket`
    # doesn't find sockets that have not been garbage collected yet.
    proxy1.close()
    proxy1.connection_pool.disconnect()
    nconnections -= 1
    del proxy1

    proxy3 = proxy2.connection_pool.create_single_connection_proxy()
    nconnections += 1
    assert proxy3.client_getname() == client_name
    assert count_clients(proxy3) == nconnections
    assert proxy2 is not proxy3

    proxy4 = proxy2.connection_pool.create_single_connection_proxy()
    nconnections += 1
    assert proxy4.client_getname() == client_name
    assert count_clients(proxy4) == nconnections
    assert proxy3 is not proxy4

    proxy5 = new_beacon_connection.get_redis_proxy(db=1)
    nconnections = 1
    assert proxy5.client_getname() == client_name
    assert count_clients(proxy5) == nconnections
    assert proxy2 is not proxy5


def test_redis_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    proxy.set("value", 0)

    def modify_value():
        proxy.incr("value")

    glts = [gevent.spawn(modify_value) for _ in range(100)]
    gevent.joinall(glts, raise_error=True)
    assert proxy.get("value") == b"100"


def test_caching_proxy(new_beacon_connection):
    proxy = new_beacon_connection.get_caching_redis_proxy()
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 0

    proxy.set("value", 1)
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 1

    proxy.connection_pool.disconnect()
    assert not proxy.connection_pool.db_cache.enabled
    with pytest.raises(RedisCacheError):
        len(proxy.connection_pool.db_cache)

    assert proxy.get("value") == b"1"
    assert not proxy.connection_pool.db_cache.enabled
    with pytest.raises(RedisCacheError):
        len(proxy.connection_pool.db_cache)

    proxy.connection_pool.db_cache.enable()
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 0

    proxy.get("value")
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 1


def test_caching_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_caching_redis_proxy()
    proxy.set("value", 0)

    def modify_value():
        proxy.testincr("value")

    glts = [gevent.spawn(modify_value) for _ in range(100)]
    gevent.joinall(glts, raise_error=True)
    assert proxy.get("value") == b"100"


def test_caching_proxy_concurrency_shared_pool(new_beacon_connection):
    proxy = new_beacon_connection.get_caching_redis_proxy()
    proxy.set("value", 0)
    proxies = [proxy.connection_pool.create_proxy() for _ in range(100)]
    assert proxies[0] is not proxies[1]
    assert proxies[0].connection_pool is proxies[1].connection_pool

    def modify_value(proxy):
        proxy.testincr("value")

    glts = [gevent.spawn(modify_value, proxy) for proxy in proxies]
    gevent.joinall(glts, raise_error=True)
    for proxy in proxies:
        assert proxy.get("value") == b"100"


def test_caching_proxy_concurrency_multi_pool(new_beacon_connection):
    proxies = [
        new_beacon_connection.get_caching_redis_proxy(shared_cache=False)
        for _ in range(100)
    ]
    assert proxies[0] is not proxies[1]
    assert proxies[0].connection_pool is not proxies[1].connection_pool
    try:
        proxies[0].set("value", 0)

        def modify_value(proxy):
            proxy.incr("value")

        glts = [gevent.spawn(modify_value, proxy) for proxy in proxies]
        gevent.joinall(glts, raise_error=True)
        for proxy in proxies:
            with gevent.Timeout(3):
                # Wait for Redis key invalidation
                while proxy.get("value") != b"100":
                    gevent.sleep(0.1)
            assert len(proxy.connection_pool.db_cache) == 1
    finally:
        # Close while we still have references to the proxies so
        # that the beacon connection can do its job cleaning them up
        new_beacon_connection.close()


def test_caching_proxy_key_invalidation(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    caching_proxy = new_beacon_connection.get_caching_redis_proxy()

    proxy.set("value", 1)
    assert caching_proxy.get("value") == b"1"
    assert len(caching_proxy.connection_pool.db_cache) == 1

    proxy.set("value", 2)
    with gevent.Timeout(3):
        # Wait for Redis key invalidation
        while caching_proxy.connection_pool.db_cache:
            gevent.sleep(0.1)
    assert caching_proxy.get("value") == b"2"

    caching_proxy.connection_pool.disable_caching()
    assert caching_proxy.get("value") == b"2"

    proxy.set("value", 3)
    assert caching_proxy.get("value") == b"3"

    caching_proxy.connection_pool.disable_caching()
    proxy.set("value", 4)
    assert caching_proxy.get("value") == b"4"

    proxy.set("value", 5)
    caching_proxy.connection_pool.enable_caching()
    assert caching_proxy.get("value") == b"5"


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
