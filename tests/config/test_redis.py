# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import socket
import gevent
import pytest

from bliss.config.conductor.redis_caching import RedisCacheError


def test_redis_connections(new_beacon_connection):
    # This test checks with the Redis server how many clients are connected.
    # Note that to ask for the clients, you need to make a connection as well.

    client_name = f"{socket.gethostname()}:{os.getpid()}"
    assert new_beacon_connection.get_client_name() == client_name

    def count_clients(proxy):
        # Only the ones from the current process. For example the tango
        # database could access Redis.
        return len(
            [client for client in proxy.client_list() if client["name"] == client_name]
        )

    proxy1 = new_beacon_connection.get_redis_proxy()
    nconnections = 1
    assert proxy1.client_getname() == client_name
    assert count_clients(proxy1) == nconnections

    new_beacon_connection.close_all_redis_connections()
    nconnections = 0
    assert proxy1.client_getname() == client_name
    nconnections += 1
    assert count_clients(proxy1) == nconnections

    proxy2 = new_beacon_connection.get_redis_proxy()
    assert proxy2.client_getname() == client_name
    assert count_clients(proxy2) == nconnections
    assert proxy1 is not proxy2
    assert proxy2 is new_beacon_connection.get_redis_proxy()

    # The Beacon connection manages Redis connection cleanup but after
    # calling `close_all_redis_connections` any existing proxy that makes
    # new connections needs to cleanup itself. This will happen on garbage
    # collection anyway but do it explicitly here so `clean_socket`
    # doesn't find sockets that have not been garbage collected yet.
    proxy1.close()
    proxy1.connection_pool.disconnect()
    nconnections -= 1
    del proxy1

    proxy3 = new_beacon_connection.get_redis_proxy(shared=False)
    nconnections += 1
    assert proxy3.client_getname() == client_name
    assert count_clients(proxy3) == nconnections
    assert proxy2 is not proxy3

    proxy4 = new_beacon_connection.get_redis_proxy(caching=True)
    nconnections += 2  # a caching proxy holds a 1 pubsub and 1 tracking connection
    # For the `client_getname` it reuses a connection from the pool
    assert proxy4.client_getname() == client_name
    assert count_clients(proxy4) == nconnections
    assert proxy3 is not proxy4

    proxy5 = new_beacon_connection.get_redis_proxy(db=1)
    nconnections = 1
    assert proxy5.client_getname() == client_name
    assert count_clients(proxy5) == nconnections
    assert proxy2 is not proxy5


@pytest.mark.parametrize("caching", [False, True])
def test_redis_connection_pool(new_beacon_connection, caching):
    proxy = new_beacon_connection.get_redis_proxy(caching=caching)

    used_before = proxy.connection_pool._in_use_connections

    def make_connections(nconnections=10):
        connections = []
        for _ in range(nconnections // 2):
            connections.append(proxy.connection_pool.get_connection(None))
            # gevent.sleep()  # commenting this line produces #2428
        proxy.connection_pool.safe_disconnect()
        for _ in range(nconnections // 2):
            connections.append(proxy.connection_pool.get_connection(None))
            gevent.sleep()
        for connection in connections:
            proxy.connection_pool.release(connection)
            gevent.sleep()
        connections = None

    glts = [gevent.spawn(make_connections) for _ in range(50)]
    gevent.joinall(glts, timeout=10, raise_error=True)
    new_used = proxy.connection_pool._in_use_connections - used_before
    assert not new_used
    if not caching:
        assert not proxy.connection_pool._closing_connections


def test_redis_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    proxy.set("dbkey", 0)

    def modify_value():
        proxy.incr("dbkey")

    glts = [gevent.spawn(modify_value) for _ in range(100)]
    gevent.joinall(glts, timeout=10, raise_error=True)
    assert proxy.get("dbkey") == b"100"


def test_async_proxy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()

    async_proxy = proxy.pipeline()
    async_proxy.set("dbkey", 0)
    ntotal = 0

    def cb(n):
        nonlocal ntotal
        ntotal += n

    async_proxy.add_execute_callback(cb, 3)
    async_proxy.add_execute_callback(cb, -1)

    assert not proxy.exists("dbkey")
    assert ntotal == 0

    async_proxy.execute()

    assert proxy.exists("dbkey")
    assert ntotal == 2


def test_caching_proxy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy(caching=True)
    assert proxy.db_cache.connected
    assert len(proxy.db_cache) == 0

    proxy.set("dbkey", 1)
    assert len(proxy.db_cache) == 1
    assert proxy.get("dbkey") == 1

    proxy.disable_caching()
    assert proxy.get("dbkey") == b"1"
    assert not proxy.db_cache.connected
    with pytest.raises(RedisCacheError):
        len(proxy.db_cache)

    proxy.enable_caching()
    assert proxy.db_cache.connected
    assert len(proxy.db_cache) == 0
    assert proxy.get("dbkey") == b"1"
    assert len(proxy.db_cache) == 1

    proxy.db_cache.connection.disconnect()
    assert proxy.db_cache.connected
    assert len(proxy.db_cache) == 1
    assert proxy.get("dbkey") == b"1"

    proxy.db_cache.disconnect()
    assert not proxy.db_cache.connected
    with pytest.raises(RedisCacheError):
        len(proxy.db_cache) == 1

    proxy.enable_caching()
    assert proxy.get("dbkey") == b"1"
    assert len(proxy.db_cache) == 1

    proxy.connection_pool.disconnect()
    with gevent.Timeout(3):
        while proxy.db_cache.connected:
            gevent.sleep(0.1)
    with pytest.raises(RedisCacheError):
        len(proxy.db_cache)


def test_caching_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy(caching=True)
    proxy.set("dbkey", 0)

    def modify_value():
        proxy.testincr("dbkey")

    glts = [gevent.spawn(modify_value) for _ in range(100)]
    gevent.joinall(glts, timeout=10, raise_error=True)
    assert proxy.get("dbkey") == b"100"


def test_async_caching_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy(caching=True)

    async_proxy = proxy.pipeline()

    for i in range(50):
        async_proxy.set("dbkey" + str(i), i)
    assert len(proxy.db_cache) == 0

    async_proxy.execute()

    # There shouldn't be any key invalidation but wait a bit to make sure
    gevent.sleep(1)

    assert len(proxy.db_cache) == 50


def test_caching_proxy_concurrency_multi_cache(new_beacon_connection):
    proxies = [
        new_beacon_connection.get_redis_proxy(caching=True, shared=False)
        for _ in range(100)
    ]
    assert proxies[0] is not proxies[1]
    assert proxies[0].connection_pool is proxies[1].connection_pool
    try:
        proxies[0].set("dbkey", 0)

        def modify_value(proxy):
            proxy.incr("dbkey")

        glts = [gevent.spawn(modify_value, proxy) for proxy in proxies]
        gevent.joinall(glts, timeout=10, raise_error=True)
        for proxy in proxies:
            with gevent.Timeout(3):
                # Wait for Redis key invalidation
                while proxy.get("dbkey") != b"100":
                    gevent.sleep(0.1)
            assert len(proxy.db_cache) == 1
    finally:
        # Close while we still have references to the proxies so
        # that the beacon connection can do its job cleaning them up
        new_beacon_connection.close()


def test_caching_proxy_key_invalidation(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    caching_proxy = new_beacon_connection.get_redis_proxy(caching=True)

    proxy.set("dbkey", 1)
    assert caching_proxy.get("dbkey") == b"1"
    assert len(caching_proxy.db_cache) == 1

    proxy.set("dbkey", 2)
    with gevent.Timeout(3):
        # Wait for Redis key invalidation
        while caching_proxy.db_cache:
            gevent.sleep(0.1)
    assert caching_proxy.get("dbkey") == b"2"

    caching_proxy.disable_caching()
    assert caching_proxy.get("dbkey") == b"2"

    proxy.set("dbkey", 3)
    assert caching_proxy.get("dbkey") == b"3"

    caching_proxy.disable_caching()
    proxy.set("dbkey", 4)
    assert caching_proxy.get("dbkey") == b"4"

    proxy.set("dbkey", 5)
    caching_proxy.enable_caching()
    assert caching_proxy.get("dbkey") == b"5"


@pytest.mark.parametrize("caching", [False, True])
def test_rotating_async_proxy(new_beacon_connection, caching):
    if caching:
        proxy = new_beacon_connection.get_redis_proxy(caching=caching)
    else:
        proxy = new_beacon_connection.get_redis_proxy()
    unlimited = 1e10
    event = {"field": "value"}

    # Validate rotation upon maximum stream events
    mgr = proxy.rotating_pipeline(
        max_time=unlimited, max_bytes=unlimited, max_stream_events=3
    )
    streamname = "stream1"
    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)
        nbytes_per_event = async_proxy._nbytes
        async_proxy.xadd(streamname, event)

    assert not proxy.exists(streamname)

    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)

    with gevent.Timeout(3):
        while not proxy.exists(streamname):
            gevent.sleep(0.1)

    # Validate rotation upon flushing
    streamname = "stream2"
    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)

    assert not proxy.exists(streamname)
    mgr.flush()
    assert proxy.exists(streamname)

    # Validate rotation upon bytes reached
    mgr = proxy.rotating_pipeline(
        max_time=unlimited, max_bytes=3 * nbytes_per_event, max_stream_events=unlimited
    )

    streamname = "stream3"
    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)
        async_proxy.xadd(streamname, event)

    assert not proxy.exists(streamname)

    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)

    with gevent.Timeout(3):
        while not proxy.exists(streamname):
            gevent.sleep(0.1)

    mgr.flush()  # stop background task

    # Validate rotation upon time reached
    mgr = proxy.rotating_pipeline(
        max_time=1, max_bytes=unlimited, max_stream_events=unlimited
    )

    streamname = "stream4"

    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)

    assert not proxy.exists(streamname)
    gevent.sleep(1)

    with gevent.Timeout(3):
        while not proxy.exists(streamname):
            gevent.sleep(0.1)

    mgr.flush()  # stop background task

    # Validate no limits
    mgr = proxy.rotating_pipeline(max_time=None, max_bytes=None, max_stream_events=None)

    streamname = "stream5"

    with mgr.async_proxy() as async_proxy:
        async_proxy.xadd(streamname, event)

    with gevent.Timeout(3):
        while not proxy.exists(streamname):
            gevent.sleep(0.1)

    mgr.flush()  # stop background task
