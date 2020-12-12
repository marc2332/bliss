# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import enum
import weakref
import fnmatch
import gevent
from functools import wraps
import redis
import redis.client
from collections.abc import MutableMapping


"""Implementation of different Redis proxy. Note that a proxy does not
hold any connections, except for the SingleRedisConnectionProxy.
"""


class AsyncRedisDbProxy(redis.client.Pipeline):
    """All redis commands are executed asynchronously. Call `execute`
    to execute the commands or `reset` to cancel them.

    As this takes a fixed connection from the connection pool, it
    is not greenlet-safe.
    """

    def pipeline(self, transaction=True, shard_hint=None):
        return self.__class__(
            self.connection_pool, self.response_callbacks, transaction, shard_hint
        )


class RedisDbProxy(redis.Redis):
    """A proxy to a particular Redis server and database as determined
    by the connection pool.

    The `close` method, called upon garbage collection, will return any
    `redis.connection.Connection` instance this proxy may have back to
    its connection pool. This does not close the connection.

    The method `pipeline` returns a `redis.client.Pipeline` instance which
    behaves like a proxy, except that all `execute_command` calls are buffered
    until `execute` is called. It also works as a context manager: calls
    `execute` on finalization.

    The `AsyncRedisDbProxy` instance uses the same connection pool.
    The `AsyncRedisDbProxy` instance is NOT greenlet-safe.
    """

    def __init__(self, pool, async_class=AsyncRedisDbProxy, **kw):
        self._async_class = async_class
        super().__init__(connection_pool=pool, **kw)

    def pipeline(self, transaction=True, shard_hint=None):
        return self._async_class(
            self.connection_pool, self.response_callbacks, transaction, shard_hint
        )


class SafeRedisDbProxy(RedisDbProxy):
    """It gets a Connection from the pool every time it executes a command.
    Therefore it is greenlet-safe: each concurrent command is executed using
    a different connection.
    """

    def __init__(self, *args, **kw):
        kw["single_connection_client"] = False
        super().__init__(*args, **kw)


class SingleRedisConnectionProxy(RedisDbProxy):
    """It gets a connection from the pool during instantiation and holds that
    connection until `close` is called (called upon garbage collection).
    Since `redis.connection.Connection` is NOT greenlet-safe, neither is
    `SingleRedisConnectionProxy`.

    Warning: the `AsyncRedisDbProxy` instance gets a new connection
    from the connection pool.
    """

    def __init__(self, *args, **kw):
        kw["single_connection_client"] = True
        super().__init__(*args, **kw)


def caching_command(func):
    """Wraps all Redis commands that need caching and protects the cache
    from concurrent access.

    When the caching is disabled for CachingRedisDbProxy, this decorator
    forwards all commands to the wrapper proxy.
    """

    @wraps(func)
    def f(self, *args, **kwargs):
        with self._cache_lock:
            with self._proxy_lock:
                if self.caching_is_enabled:
                    return func(self, *args, **kwargs)
        # Call the parent's method
        return getattr(super(self.__class__, self), func.__name__)(*args, **kwargs)

    return f


def access_cache(func):
    """To protects the cache from concurrent access.
    """

    @wraps(func)
    def f(self, *args, **kwargs):
        with self._cache_lock:
            with self._proxy_lock:
                return func(self, *args, **kwargs)

    return f


class CachedSettingsDict(MutableMapping):
    """Dictionary of BaseSettings that are cached. This is used so that
    the associated Redis keys are removed from the cache when the setting
    is removed from CachedSettingsDict.
    """

    def __init__(self, db_cache):
        self._cached_settings = weakref.WeakKeyDictionary()
        self._db_cache = db_cache

    def __setitem__(self, key, value):
        self._cached_settings[key] = value

    def __getitem__(self, key):
        return self._cached_settings[key]

    def __delitem__(self, key):
        name, _ = self._cached_settings[key]
        del self._cached_settings[key]
        self._db_cache.pop(name, None)

    def __iter__(self):
        return iter(self._cached_settings)

    def __len__(self):
        return len(self._cached_settings)


class CachingAsyncRedisDbProxy(AsyncRedisDbProxy):
    """Handle cache manipulation asynchronously, just like the Redis
    commands (i.e. execute upon calling `execute` and drop upon `reset`).
    """

    def __init__(self, *args, **kw):
        self._db_cache_tasks = list()
        super().__init__(*args, **kw)

    def reset(self):
        self._db_cache_tasks.clear()
        super().reset()

    @property
    def _db_cache(self):
        return self.connection_pool.db_cache

    def delete(self, name):
        def delete_func():
            self._db_cache.pop(name, None)

        self._db_cache_tasks.append(delete_func)
        return super().delete(name)

    def set(self, name, value, *args, **kwargs):
        def set_func():
            self._db_cache[name] = value

        self._db_cache_tasks.append(set_func)
        return super().set(name, value, *args, **kwargs)

    def hdel(self, name, *keys):
        def hdel_func():
            cached_dict = self._db_cache.get(name)
            if cached_dict is not None:
                for k in keys:
                    cached_dict.pop(k.encode(), None)

        self._db_cache_tasks.append(hdel_func)
        return super().hdel(name, *keys)

    def hset(self, name, key, value):
        def hset_func():
            cached_dict = self._db_cache.get(name)
            if cached_dict is not None:
                cached_dict[key.encode()] = value

        self._db_cache_tasks.append(hset_func)
        return super().hset(name, key, value)

    def hmset(self, name, mapping):
        def hmset_func():
            cached_dict = self._db_cache.get(name)
            if cached_dict is not None:
                cached_dict.update((k.encode(), v) for k, v in mapping.items())

        self._db_cache_tasks.append(hmset_func)
        return super().hmset(name, mapping)

    def lpop(self, name, *values):
        def lpop_func():
            cached_list = self._db_cache.get(name)
            if cached_list is not None:
                try:
                    cached_list.pop(0)
                except IndexError:
                    pass

        self._db_cache_tasks.append(lpop_func)
        return super().lpop(name, *values)

    def lpush(self, name, *values):
        def lpush_func():
            cache_list = self._db_cache.get(name)
            if cache_list is not None:
                for v in values:
                    cache_list.insert(0, v)

        self._db_cache_tasks.append(lpush_func)
        return super().lpush(name, *values)

    def rpush(self, name, *values):
        def rpush_func():
            cache_list = self._db_cache.get(name)
            if cache_list is not None:
                cache_list.extend(values)

        self._db_cache_tasks.append(rpush_func)
        return super().rpush(name, *values)

    def rpop(self, name):
        def rpop_func():
            cache_list = self._db_cache.get(name)
            if cache_list is not None:
                try:
                    cache_list.pop(-1)
                except IndexError:
                    pass

        self._db_cache_tasks.append(rpop_func)
        return super().rpop(name)

    def lrem(self, name, *args):
        def clear_cache():
            self._db_cache.pop(name, None)

        self._db_cache_tasks.append(clear_cache)
        return super().lrem(name, *args)

    def execute(self):
        # Apply all commands on the cached database
        for task in self._db_cache_tasks:
            task()
        self._db_cache_tasks.clear()
        # Apply all commands to the server database
        return super().execute()


class CachingRedisDbProxy(SafeRedisDbProxy):
    """Setting/getting Redis keys through this proxy will cache them in
    the connection pool's cache.

    When settings are registered with `add_prefetch`, they will be fetched
    when they are missing from the cache. It is not required to have those
    settings cached however. It just refetches whenever invalidated due
    to changes in the Redis database.

    This could be done only if Redis version >= 6.
    """

    TYPE = enum.Enum("TYPE", "HASH KEY QUEUE ZSET")

    def __init__(self, connection_pool):
        self._proxy_lock = gevent.lock.RLock()
        self._enable_caching = True
        self._cached_settings = CachedSettingsDict(connection_pool.db_cache)
        super().__init__(connection_pool, async_class=CachingAsyncRedisDbProxy)

    @property
    def _db_cache(self):
        return self.connection_pool.db_cache

    @property
    def _cache_lock(self):
        return self._db_cache.cache_lock

    @property
    def ncached(self):
        return len(self._cached_settings)

    @property
    def caching_is_enabled(self):
        return self._enable_caching and self._db_cache.enabled

    def disable_caching(self, disable_pool=True):
        """After this command, the proxy behaves like `SafeRedisDbProxy`.
        All pre-fetched objects will be removed.

        When disable_pool=True caching will be disabled for all proxies
        to the connection pool we have a reference too.
        """
        self._enable_caching = False
        self.clear_all_prefetch()
        if disable_pool:
            self.connection_pool.disable_caching()

    def add_prefetch(self, *objects):
        """Adds object to be pre-fetched in block in case of any cache failed.
        Objects will be always kept in memory even if they are not accessed.
        Redis communication happens in the method so not not execute in
        a pipeline.

        Any setting can be added to be pre-fetched.
        """
        from bliss.config import settings

        for obj in objects:
            name = obj.name
            if not isinstance(name, (str, bytes)):
                raise TypeError(
                    f"Cannot prefetch {obj} inside an asynchronous Redis pipeline"
                )
            if isinstance(obj, settings.SimpleSetting):
                self._cached_settings[obj] = (name, self.TYPE.KEY)
            elif isinstance(obj, settings.BaseHashSetting):
                self._cached_settings[obj] = (name, self.TYPE.HASH)
            elif isinstance(obj, settings.Struct):
                self._cached_settings[obj._proxy] = (name, self.TYPE.HASH)
            else:
                raise ValueError(f"Type not yet managed {obj}")

    def remove_prefetch(self, *objects):
        for obj in objects:
            self._cached_settings.pop(obj, None)

    def clear_all_prefetch(self):
        self._cached_settings.clear()

    @caching_command
    def evalsha(self, script_name, n, *args):
        keys = args[:n]
        super().evalsha(script_name, n, *args)
        # invalidate cache for those keys
        for k in keys:
            self._db_cache.pop(k, None)

    @caching_command
    def delete(self, name):
        self._db_cache.pop(name, None)
        super().delete(name)

    # KEY
    @caching_command
    def get(self, name):
        return self._get_cache_key(name)

    @caching_command
    def set(self, name, value, ex=None, px=None, nx=False, xx=False):
        return_val = super().set(name, value, ex, px, nx, xx)
        self._db_cache[name] = value
        return return_val

    @caching_command
    def testincr(self, name, amount=1):
        # Just for concurrancy testing. The real incr needs to be atomic
        # so we can't do it through the cache.
        result = super().incr(name, amount=amount)
        self.set(name, b"%d" % result)
        return result

    # HASH
    @caching_command
    def hdel(self, name, *keys):
        return_val = super().hdel(name, *keys)
        cached_dict = self._get_cache_dict(name)
        for k in keys:
            cached_dict.pop(k.encode(), None)
        return return_val

    @caching_command
    def hexists(self, name, key):
        cached_dict = self._get_cache_dict(name)
        return key.encode() in cached_dict

    @caching_command
    def hget(self, name, key):
        cached_dict = self._get_cache_dict(name)
        return cached_dict.get(key.encode() if isinstance(key, str) else key)

    @caching_command
    def hgetall(self, name):
        return self._get_cache_dict(name)

    @caching_command
    def hlen(self, name):
        cached_dict = self._get_cache_dict(name)
        return len(cached_dict)

    @caching_command
    def hset(self, name, key, value):
        return_val = super().hset(name, key, value)
        cached_dict = self._get_cache_dict(name)
        cached_dict[key.encode()] = value
        return return_val

    @caching_command
    def hmset(self, name, mapping):
        return_val = super().hmset(name, mapping)
        cached_dict = self._get_cache_dict(name)
        cached_dict.update((k.encode(), v) for k, v in mapping.items())
        return return_val

    @caching_command
    def hscan(self, name, cursor=0, match=None, count=None):
        cached_dict = self._get_cache_dict(name)
        if count is None or count >= len(cached_dict):
            if match is None:
                return 0, cached_dict
            else:
                return (
                    0,
                    {
                        k: v
                        for k, v in cached_dict.items()
                        if fnmatch.fnmatch(k.decode(), match)
                    },
                )
        else:
            # This part is really not optimize but it's not use
            # in the base code.
            key_list = list(cached_dict.keys())
            return_dict = dict()
            index = cursor
            while count:
                try:
                    key = key_list[index]
                except IndexError:
                    return 0, return_dict
                index += 1
                if match is not None and not fnmatch.fnmatch(key.decode(), match):
                    continue
                return_dict[key] = cached_dict[key]
                count -= 1
            return index, return_dict

    # LIST COMMANDS
    @caching_command
    def lindex(self, name, index):
        cache_list = self._get_cache_list(name)
        return cache_list[index]

    @caching_command
    def llen(self, name):
        cache_list = self._get_cache_list(name)
        return len(cache_list)

    @caching_command
    def lpop(self, name):
        return_val = super().lpop(name)
        cache_list = self._get_cache_list(name)
        if cache_list and return_val == cache_list[0]:
            cache_list.pop(0)
        return return_val

    @caching_command
    def lpush(self, name, *values):
        return_val = super().lpush(name, *values)
        cache_list = self._get_cache_list(name)
        for v in values:
            cache_list.insert(0, v)
        return return_val

    @caching_command
    def rpush(self, name, *values):
        return_val = super().lpush(name, *values)
        cache_list = self._get_cache_list(name)
        cache_list.extend(values)
        return return_val

    @caching_command
    def lrange(self, name, start, end):
        cache_list = self._get_cache_list(name)
        if end == -1:
            end = len(cache_list)
        else:
            end += 1
        return cache_list[start:end]

    @caching_command
    def rpop(self, name):
        return_val = super().rpop(name)
        cache_list = self._get_cache_list(name)
        if cache_list and return_val == cache_list[-1]:
            cache_list.pop(-1)
        return return_val

    @caching_command
    def lrem(self, name, count, value):
        return_val = super().lrem(name, count, value)
        if count >= 0:
            cache_list = self._get_cache_list(name)
            for i in range(return_val):
                try:
                    cache_list.remove(value)
                except ValueError:  # already removed
                    pass
        else:  # re-synchronization on next get
            self._db_cache.pop(name, None)

    # SORTED SET COMMANDS
    @caching_command
    def zrange(
        self, name, start, end, desc=False, withscores=False, score_cast_func=float
    ):
        cache_sorted_set = self._get_cache_sorted_set(name)
        if end == -1:
            end = len(cache_sorted_set)
        else:
            end += 1
        if desc:
            items = reversed(cache_sorted_set.items())
        else:
            items = cache_sorted_set.items()

        if withscores:
            return list(items[start:end])
        return list(x for x, y in items)

    def _get_cache_dict(self, name):
        cached_dict = self._db_cache.get(name)
        if cached_dict is None:
            cached_dict = self._fill_cache(name, self.TYPE.HASH)
        return cached_dict

    def _get_cache_key(self, name):
        value = self._db_cache.get(name)
        if value is None and name not in self._db_cache:
            value = self._fill_cache(name, self.TYPE.KEY)
        return value

    def _get_cache_list(self, name):
        values = self._db_cache.get(name)
        if values is None:
            values = self._fill_cache(name, self.TYPE.QUEUE)
        return values

    def _get_cache_sorted_set(self, name):
        values = self._db_cache.get(name)
        if values is None:
            # return a list with name and score
            # change it to dict
            values = dict(self._fill_cache(name, self.TYPE.ZSET))
            self._db_cache[name] = values
        return values

    @access_cache
    def _fill_cache(self, name, object_type):
        """This method gets the value of Redis key "name" from the Redis
        database and caches it. In addition we will fetch all the
        "prefetch" keys which have not been cached yet (or were invalidated).

        :param str name: Redis key name
        :param TYPE object_type: Redis value type
        :returns: the value of the Redis key
        """
        cached_settings = {name: object_type}
        fetch_names = {name}

        # Add prefetch objects that are currently not cached
        cached_settings.update(
            {name: obj_type for name, obj_type in self._cached_settings.values()}
        )
        fetch_names.update(cached_settings.keys() - self._db_cache.keys())

        # Fetch all values from Redis
        pipeline = self.pipeline()
        for obj_name in fetch_names:
            obj_type = cached_settings[obj_name]
            if obj_type == self.TYPE.HASH:
                pipeline.hgetall(obj_name)
            elif obj_type == self.TYPE.KEY:
                pipeline.get(obj_name)
            elif obj_type == self.TYPE.QUEUE:
                pipeline.lrange(obj_name, 0, -1)
            elif obj_type == self.TYPE.ZSET:
                pipeline.zrange(obj_name, 0, -1, withscores=True)
        pipeline_result = pipeline.execute()

        # Fill the cache with those values
        for obj_name, result in zip(fetch_names, pipeline_result):
            self._db_cache[obj_name] = result

        # Return the value of the key we actually asked for
        return self._db_cache[name]
