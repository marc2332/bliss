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
    proxy.set("dbkey", 0)

    def modify_value():
        proxy.incr("dbkey")

    glts = [gevent.spawn(modify_value) for _ in range(100)]
    gevent.joinall(glts, raise_error=True)
    assert proxy.get("dbkey") == b"100"


def test_async_proxy(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    proxy.delete("dbkey")

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
    proxy = new_beacon_connection.get_caching_redis_proxy()
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 0

    proxy.set("dbkey", 1)
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 1

    proxy.connection_pool.disconnect()
    assert not proxy.connection_pool.db_cache.enabled
    with pytest.raises(RedisCacheError):
        len(proxy.connection_pool.db_cache)

    assert proxy.get("dbkey") == b"1"
    assert not proxy.connection_pool.db_cache.enabled
    with pytest.raises(RedisCacheError):
        len(proxy.connection_pool.db_cache)

    proxy.connection_pool.db_cache.enable()
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 0

    proxy.get("dbkey")
    assert proxy.connection_pool.db_cache.enabled
    assert len(proxy.connection_pool.db_cache) == 1


def test_caching_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_caching_redis_proxy()
    proxy.set("dbkey", 0)

    def modify_value():
        proxy.testincr("dbkey")

    glts = [gevent.spawn(modify_value) for _ in range(100)]
    gevent.joinall(glts, raise_error=True)
    assert proxy.get("dbkey") == b"100"


def test_async_caching_proxy_concurrancy(new_beacon_connection):
    proxy = new_beacon_connection.get_caching_redis_proxy().pipeline()

    for i in range(5):
        proxy.set("dbkey" + str(i), i)
    assert len(proxy.connection_pool.db_cache) == 0
    proxy.execute()
    assert len(proxy.connection_pool.db_cache) == 5


def test_caching_proxy_concurrency_shared_pool(new_beacon_connection):
    proxy = new_beacon_connection.get_caching_redis_proxy()
    proxy.set("dbkey", 0)
    proxies = [proxy.connection_pool.create_proxy() for _ in range(100)]
    assert proxies[0] is not proxies[1]
    assert proxies[0].connection_pool is proxies[1].connection_pool

    def modify_value(proxy):
        proxy.testincr("dbkey")

    glts = [gevent.spawn(modify_value, proxy) for proxy in proxies]
    gevent.joinall(glts, raise_error=True)
    for proxy in proxies:
        assert proxy.get("dbkey") == b"100"


def test_caching_proxy_concurrency_multi_pool(new_beacon_connection):
    proxies = [
        new_beacon_connection.get_caching_redis_proxy(shared_cache=False)
        for _ in range(100)
    ]
    assert proxies[0] is not proxies[1]
    assert proxies[0].connection_pool is not proxies[1].connection_pool
    try:
        proxies[0].set("dbkey", 0)

        def modify_value(proxy):
            proxy.incr("dbkey")

        glts = [gevent.spawn(modify_value, proxy) for proxy in proxies]
        gevent.joinall(glts, raise_error=True)
        for proxy in proxies:
            with gevent.Timeout(3):
                # Wait for Redis key invalidation
                while proxy.get("dbkey") != b"100":
                    gevent.sleep(0.1)
            assert len(proxy.connection_pool.db_cache) == 1
    finally:
        # Close while we still have references to the proxies so
        # that the beacon connection can do its job cleaning them up
        new_beacon_connection.close()


def test_caching_proxy_key_invalidation(new_beacon_connection):
    proxy = new_beacon_connection.get_redis_proxy()
    caching_proxy = new_beacon_connection.get_caching_redis_proxy()

    proxy.set("dbkey", 1)
    assert caching_proxy.get("dbkey") == b"1"
    assert len(caching_proxy.connection_pool.db_cache) == 1

    proxy.set("dbkey", 2)
    with gevent.Timeout(3):
        # Wait for Redis key invalidation
        while caching_proxy.connection_pool.db_cache:
            gevent.sleep(0.1)
    assert caching_proxy.get("dbkey") == b"2"

    caching_proxy.connection_pool.disable_caching()
    assert caching_proxy.get("dbkey") == b"2"

    proxy.set("dbkey", 3)
    assert caching_proxy.get("dbkey") == b"3"

    caching_proxy.connection_pool.disable_caching()
    proxy.set("dbkey", 4)
    assert caching_proxy.get("dbkey") == b"4"

    proxy.set("dbkey", 5)
    caching_proxy.connection_pool.enable_caching()
    assert caching_proxy.get("dbkey") == b"5"


def test_rotating_async_proxy(new_beacon_connection):
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
