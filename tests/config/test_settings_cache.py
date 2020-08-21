# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import itertools
import pytest
import gevent
from bliss.config.conductor import client
from bliss.config import settings, settings_cache


def test_open_close(beacon):
    db = client.get_redis_connection()
    cache = settings_cache.CacheConnection(db)
    cache.open()
    cache.close()


@pytest.mark.parametrize("redis_version", [5, 6])
def test_hash_command(beacon, redis_version):
    hash_name = "tagada"
    h = settings.HashSetting(hash_name)
    l = [chr(ord("a") + i) for i in range(26)]
    values = {"".join(k): i for i, k in enumerate(itertools.permutations(l, 2))}
    h.update(values)

    cache = settings_cache.CacheConnection(h.connection)
    if redis_version < 6:
        cache._able_to_cache = False

    assert 24 == int(cache.hget(hash_name, "az"))
    assert values == {k.decode(): int(v) for k, v in cache.hgetall(hash_name).items()}
    assert len(values) == cache.hlen(hash_name)

    cache.hset(hash_name, "truc", "123")
    assert h["truc"] == 123 == int(cache.hget(hash_name, "truc"))

    cache.hmset(hash_name, {"hello": "20", "super": "40"})
    assert h["super"] == 40

    # hscan
    cur = 0
    new_values = dict()
    while True:
        cur, d = cache.hscan(hash_name, cursor=cur)
        assert d.keys().isdisjoint(new_values.keys())
        new_values.update(d)
        if not cur:
            break

    values = h.get_all()
    new_values = {k.decode(): int(v) for k, v in new_values.items()}
    assert new_values == values

    new_values = dict()
    cur = 0
    while True:
        cur, d = cache.hscan(hash_name, cursor=cur, count=20)
        assert d.keys().isdisjoint(new_values.keys())
        new_values.update(d)

        if not cur:
            break
    assert len(new_values) == len(values)
    assert {k.decode(): int(v) for k, v in new_values.items()} == values

    cur = 0
    new_values = dict()
    while True:
        cur, d = cache.hscan(hash_name, match="a*", cursor=cur)
        new_values.update(d)
        if not cur:
            break

    assert {k.decode(): int(v) for k, v in new_values.items()} == {
        k: v for k, v in values.items() if k.startswith("a")
    }

    new_values = dict()
    cur = 0
    while True:
        cur, d = cache.hscan(hash_name, cursor=cur, match="a*", count=5)
        new_values.update(d)
        if not cur:
            break
    assert {k.decode(): int(v) for k, v in new_values.items()} == {
        k: v for k, v in values.items() if k.startswith("a")
    }

    cache.close()


@pytest.mark.parametrize("redis_version", [5, 6])
def test_simple_key(beacon, redis_version):
    key_name = "doo"
    k = settings.SimpleSetting(key_name)
    k.set("hello")

    cache = settings_cache.CacheConnection(k.connection)
    if redis_version < 6:
        cache._able_to_cache = False

    assert cache.get(key_name).decode() == "hello"

    cache.close()


def test_simple_key_synchronisation(beacon):
    key_name = "doo"
    k = settings.SimpleSetting(key_name)
    k.set("hello")

    cache = settings_cache.CacheConnection(k.connection)
    k2 = settings.SimpleSetting(key_name, connection=cache)
    assert k.get() == k2.get()

    # simulate change value from other client
    k.set("super")
    gevent.sleep(0.1)  # let the time to synchronize
    assert k.get() == k2.get()

    k2.set("mario")
    assert k.get() == k2.get()

    cache.close()


def test_hash_synchronisation(beacon):
    key_name = "what_ever"
    h = settings.HashObjSetting(key_name)
    l = [1, 2, 3]
    d = {0: 1}
    s = "super mario"
    h.update({"l": l, "d": d, "s": s})

    cache = settings_cache.CacheConnection(h.connection)
    h2 = settings.HashObjSetting(key_name, connection=cache)
    assert h2["l"] == l
    assert h2["d"] == d
    assert h2["s"] == s

    a_set = set([1, 2, 3])
    h["set"] = a_set
    gevent.sleep(0.1)  # let the time to synchronize
    assert h["set"] == h2["set"]

    h2["set2"] = a_set
    assert h["set2"] == h2["set2"]

    cache.close()


def test_empty_hash_object(beacon):
    key_name = "what_ever2"
    h = settings.HashSetting(key_name)

    cache = settings_cache.CacheConnection(h.connection)
    h2 = settings.HashSetting(key_name, connection=cache)

    # force synchronisation
    h2.get("hello")

    h["hello"] = "you"
    gevent.sleep(0.1)  # let the time to synchronize
    assert h["hello"] == h2["hello"]

    cache.close()


def test_empty_key_object(beacon):
    key_name = "super_mario"
    k = settings.SimpleSetting(key_name)

    cache = settings_cache.CacheConnection(k.connection)
    k2 = settings.SimpleSetting(key_name, connection=cache)

    # force synchronisation
    k2.get()

    k.set("bla")
    gevent.sleep(0.1)  # let the time to synchronize
    assert k.get() == k2.get()

    cache.close()


def test_prefetch_key(beacon):
    keys = [f"val_{i}" for i in range(4)]
    k = [settings.SimpleSetting(name) for name in keys]

    cache = settings_cache.CacheConnection(k[0].connection)
    k2 = [settings.SimpleSetting(name, connection=cache) for name in keys]
    cache.add_prefetch(*k2)

    # init value
    [k.set(i) for i, k in enumerate(k)]

    # generate first cache failed
    assert k2[0].get() == 0
    # check cache
    assert not set(keys) - cache._cache_values.keys()

    # remove prefetch
    # should remove cached values
    cache.remove_prefetch(*k2)
    assert not cache._cache_values

    cache.close()
