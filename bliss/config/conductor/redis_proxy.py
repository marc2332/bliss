# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import enum
import weakref
import fnmatch
import time
from functools import wraps
from collections.abc import MutableMapping
from collections import Counter
from contextlib import contextmanager
import gevent
import redis
import redis.client

from bliss.common.utils import grouped
from bliss.config.conductor import redis_caching


"""Implementation of different Redis proxy.
"""


def key_value_list_or_mapping_to_dict(key_value_list_or_mapping):
    """Helper function to convert a list key1,value1, ..., keyN, valueN to a dict,
    or to return a mapping as it is
    """
    if len(key_value_list_or_mapping) == 1:
        # must be a mapping
        assert isinstance(key_value_list_or_mapping[0], MutableMapping)
        mapping = key_value_list_or_mapping[0]
    else:
        # function parameters as key1, value1, ..., keyN, valueN
        mapping = dict(grouped(key_value_list_or_mapping, 2))
    return mapping


class AsyncRedisDbProxy(redis.client.Pipeline):
    """All redis commands are executed asynchronously. Call `execute`
    to execute the commands or `reset` to cancel them.

    As this takes a fixed connection from the connection pool, it
    is not greenlet-safe.

    Reponse callbacks are applied to the result of a certain command.
    Execute callbacks are called upon execution of the pipeline.
    """

    def __init__(
        self,
        connection_pool=None,
        response_callbacks=None,
        transaction=True,
        shard_hint=None,
    ):
        if response_callbacks is None:
            response_callbacks = dict()
        if connection_pool is None:
            raise ValueError("connection_pool not provided")
        self._execute_callbacks = list()
        super().__init__(connection_pool, response_callbacks, transaction, shard_hint)

    def pipeline(self, **kw):
        kw.setdefault("connection_pool", self.connection_pool)
        kw.setdefault("response_callbacks", self.response_callbacks)
        # Do not use `super` here or you get an instance of the base class
        return self.__class__(**kw)

    def reset(self):
        super().reset()
        self._execute_callbacks = list()

    def execute(self, **kw):
        callbacks = self._execute_callbacks
        result = super().execute(**kw)
        for func, args, kwargs in callbacks:
            func(*args, **kwargs)
        return result

    def add_execute_callback(self, func, *args, **kw):
        self._execute_callbacks.append((func, args, kw))


class MonitoringAsyncRedisDbProxy(AsyncRedisDbProxy):
    """An asynchronous Redis proxy which monitors time, total buffered
    command size and events per stream.

    Use `wait_maximum_reached` to wait until one of the monitored resources
    hit their maximum.

    Use `maximum_is_reached` to manually say the maximum is reached.
    """

    def __init__(self, **kw):
        """
        :param int or None max_stream_events: maximum event per stream
        :param int or None max_bytes: maximum on the buffered commands
        :param num or None max_time: maximum on time since first buffered command
        """
        self._max_stream_events = kw.pop("max_stream_events", None)
        self._max_bytes = kw.pop("max_bytes", None)
        self._max_time = kw.pop("max_time", None)
        self._max_event = gevent.event.Event()
        self._reset_monitoring()
        super().__init__(**kw)

    def wait_maximum_reached(self):
        """Wait until any of the resouce maxima is reached
        """
        return self._max_event.wait(timeout=self._time_left)

    def maximum_is_reached(self):
        """Causes an existing or future `wait_maximum_reached` call to
        return immediately (until reset).
        """
        self._max_event.set()

    def _reset_monitoring(self):
        """Restart resource monitoring
        """
        self._nbytes = 0
        self._nstream_events = Counter()
        self._start_time = None
        self._max_event.clear()
        if (
            self._max_stream_events is None
            and self._max_bytes is None
            and self._max_time is None
        ):
            self._max_event.set()

    def reset(self):
        super().reset()
        self._reset_monitoring()

    def xadd(self, name, fields, **kw):
        super().xadd(name, fields, **kw)
        self._monitor_stream_events(name)

    def pipeline_execute_command(self, *args, **options):
        super().pipeline_execute_command(*args, **options)
        self._monitor_time()
        self._monitor_data_size(args)

    def _monitor_stream_events(self, name):
        """Increase the stream counter and check maximum
        """
        if self._max_event.is_set() or self._max_stream_events is None:
            return
        self._nstream_events[name] += 1
        if self._nstream_events[name] >= self._max_stream_events:
            self.maximum_is_reached()

    def _monitor_data_size(self, data):
        """Increase the total buffered command size and check maximum
        """
        if self._max_event.is_set() or self._max_bytes is None:
            return
        self._nbytes += sys.getsizeof(data)
        if self._nbytes >= self._max_bytes:
            self.maximum_is_reached()

    def _monitor_time(self):
        """Start timing when needed and check time maximum
        """
        if self._time_left == 0:
            self.maximum_is_reached()

    @property
    def _time_left(self):
        """Returns `None` when not monitoring time or some maximum is
        already reached.
        """
        if self._max_event.is_set() or self._max_time is None:
            return None
        if self._start_time is None:
            self._start_time = time.time()
        return max(self._max_time - (time.time() - self._start_time), 0)

    def pipeline(self, **kw):
        kw.setdefault("max_stream_events", self._max_stream_events)
        kw.setdefault("max_bytes", self._max_bytes)
        kw.setdefault("max_time", self._max_time)
        return super().pipeline(**kw)


class MonitoringAsyncRedisDbProxyManager:
    """Rotate asynchronous Redis proxies and execute in the background
    upon rotation. Usage:

        mgr = proxy.rotating_pipeline()
        with mgr.async_proxy() as async_proxy:
            async_proxy.set("key1", "value1")
            async_proxy.xadd("key2", {"key": "value2"})

        with mgr.async_proxy() as async_proxy:
            async_proxy.set("key3", "value3")
            async_proxy.xadd("key4", {"key": "value4"})
            async_proxy.add_execute_callback(func, "var1", kwarg1="kwarg1")

        mgr.flush()  # to force a pipeline execution

    The underlying pipeline is rotated and executed when `flush` is called
    or when the pipeline has reached its rotating criterea (see MonitoringAsyncRedisDbProxy).
    """

    def __init__(self, async_proxy: MonitoringAsyncRedisDbProxy):
        self._execution_task = None
        self._rotation_async_proxy = async_proxy
        self._rotating_lock = gevent.lock.Semaphore()

    @contextmanager
    def async_proxy(self):
        with self._rotating_lock:
            yield self._rotation_async_proxy
            self._ensure_execution_task()

    def flush(self, blocking=True, timeout=None, raise_error=False):
        """Finish the execution task and thereby forcing execution of
        the pipeline.
        """
        with self._rotating_lock:
            self._rotation_async_proxy.maximum_is_reached()
            task = self._ensure_execution_task()
        if task is not None and blocking:
            if raise_error:
                task.get(timeout=timeout)
            else:
                task.join(timeout=timeout)
        return task

    def _ensure_execution_task(self):
        """Return the current pipeline execution task and make sure it
        is running when there are commands in the pipeline.

        Before starting the execution of a new task, an exception is
        raised when the previos task failed.
        """
        # Return when task is running or no commands in the pipeline
        if self._execution_task or not len(self._rotation_async_proxy):
            return self._execution_task

        # Raise error when the previous task failed
        if self._execution_task is not None:
            self._execution_task.get()

        # Swap the current pipeline and launch the execution task
        self._execution_task = gevent.spawn(self._execution_loop)
        return self._execution_task

    def _execution_loop(self):
        """Execute the pipeline and swap it. Repeat until no more commands
        in the pipeline. Before executing the pipeline, it waits for the
        rotation event.
        """
        while True:
            if not len(self._rotation_async_proxy):
                break
            self._rotation_async_proxy.wait_maximum_reached()
            async_proxy = self._rotation_async_proxy
            self._rotation_async_proxy = async_proxy.pipeline()
            async_proxy.execute()


class RedisDbProxyBase(redis.Redis):
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

    def __init__(
        self,
        connection_pool=None,
        async_class=AsyncRedisDbProxy,
        monitoring_async_class=MonitoringAsyncRedisDbProxy,
        **kw,
    ):
        self._async_class = async_class
        self._monitoring_async_class = monitoring_async_class
        if connection_pool is None:
            raise ValueError("connection_pool not provided")
        super().__init__(connection_pool=connection_pool, **kw)

    def hset(self, name, *key_value_list_or_mapping, mapping=None):
        """hset method, compatible with deprecated hmset

        If mapping is given: just call redis.Redis "hset"
        If not mapping is given, individual key, value args can be passed,
        or a dictionary
        """
        if mapping is None:
            mapping = key_value_list_or_mapping_to_dict(key_value_list_or_mapping)

        return super().hset(name, mapping=mapping)

    def pipeline(self, **kw):
        kw.setdefault("connection_pool", self.connection_pool)
        kw.setdefault("response_callbacks", self.response_callbacks)
        return self._async_class(**kw)

    def rotating_pipeline(self, **kw):
        kw.setdefault("connection_pool", self.connection_pool)
        kw.setdefault("response_callbacks", self.response_callbacks)
        async_proxy = self._monitoring_async_class(**kw)
        return MonitoringAsyncRedisDbProxyManager(async_proxy)


class RedisDbProxy(RedisDbProxyBase):
    """It gets a Connection from the pool every time it executes a command.

    This proxy is greenlet-safe although the connections are not.
    """

    def __init__(self, *args, **kw):
        kw["single_connection_client"] = False
        super().__init__(*args, **kw)


class SingleConnectionRedisDbProxy(RedisDbProxyBase):
    """It gets a connection from the pool during instantiation and holds that
    connection until `close` is called (called upon garbage collection).

    This proxy is not greenlet-safe.

    The `AsyncRedisDbProxy` creates new connections.
    """

    def __init__(self, *args, **kw):
        kw["single_connection_client"] = True
        super().__init__(*args, **kw)


class CachingAsyncRedisDbProxy(AsyncRedisDbProxy):
    """Handle cache manipulation asynchronously, just like the Redis
    commands (i.e. execute upon calling `execute` and drop upon `reset`).
    """

    def __init__(self, root_proxy=None, **kw):
        self._root_proxy = root_proxy
        self._db_cache_tasks = list()
        self._connection = None
        super().__init__(**kw)

    def pipeline(self, **kw):
        kw.setdefault("root_proxy", self._root_proxy)
        return super().pipeline(**kw)

    @property
    def connection(self):
        if self._connection is None:
            return self._root_proxy.connection
        else:
            return self._connection

    @connection.setter
    def connection(self, value):
        self._connection = value

    @property
    def _caching_lock(self):
        return self._root_proxy._caching_lock

    @property
    def db_cache(self):
        return self._root_proxy.db_cache

    @property
    def _enable_caching(self):
        return self._root_proxy._enable_caching

    @property
    def _use_caching(self):
        return self._enable_caching and self._db_cache_tasks

    def reset(self):
        super().reset()
        self._db_cache_tasks.clear()

    def delete(self, name):
        def delete_func():
            self.db_cache.pop(name, None)

        self._db_cache_tasks.append(delete_func)
        return super().delete(name)

    def set(self, name, value, *args, **kwargs):
        def set_func():
            self.db_cache[name] = value

        self._db_cache_tasks.append(set_func)
        return super().set(name, value, *args, **kwargs)

    def hdel(self, name, *keys):
        def hdel_func():
            cached_dict = self.db_cache.get(name)
            if cached_dict is not None:
                for k in keys:
                    cached_dict.pop(k.encode(), None)

        self._db_cache_tasks.append(hdel_func)
        return super().hdel(name, *keys)

    def hset(self, name, *key_value_list_or_mapping, mapping=None):
        if mapping is None:
            mapping = key_value_list_or_mapping_to_dict(key_value_list_or_mapping)

        def hset_func():
            cached_dict = self.db_cache.get(name)
            if cached_dict is not None:
                for key, value in mapping.items():
                    cached_dict[key.encode()] = value

        self._db_cache_tasks.append(hset_func)
        return super().hset(name, mapping=mapping)

    def lpop(self, name, *values):
        def lpop_func():
            cached_list = self.db_cache.get(name)
            if cached_list is not None:
                try:
                    cached_list.pop(0)
                except IndexError:
                    pass

        self._db_cache_tasks.append(lpop_func)
        return super().lpop(name, *values)

    def lpush(self, name, *values):
        def lpush_func():
            cache_list = self.db_cache.get(name)
            if cache_list is not None:
                for v in values:
                    cache_list.insert(0, v)

        self._db_cache_tasks.append(lpush_func)
        return super().lpush(name, *values)

    def rpush(self, name, *values):
        def rpush_func():
            cache_list = self.db_cache.get(name)
            if cache_list is not None:
                cache_list.extend(values)

        self._db_cache_tasks.append(rpush_func)
        return super().rpush(name, *values)

    def rpop(self, name):
        def rpop_func():
            cache_list = self.db_cache.get(name)
            if cache_list is not None:
                try:
                    cache_list.pop(-1)
                except IndexError:
                    pass

        self._db_cache_tasks.append(rpop_func)
        return super().rpop(name)

    def lrem(self, name, *args):
        def clear_cache():
            self.db_cache.pop(name, None)

        self._db_cache_tasks.append(clear_cache)
        return super().lrem(name, *args)

    def _execute_cache_tasks(self):
        for task in self._db_cache_tasks:
            task()
        self._db_cache_tasks.clear()

    def immediate_execute_command(self, *args, **kw):
        if self._use_caching:
            with self._caching_lock:
                self._execute_cache_tasks()
                return super().immediate_execute_command(*args, **kw)
        else:
            return super().immediate_execute_command(*args, **kw)

    def execute(self, **kw):
        if self._use_caching:
            with self._caching_lock:
                self._execute_cache_tasks()
                return super().execute(**kw)
        else:
            return super().execute(**kw)


class MonitoringCachingAsyncRedisDbProxy(
    CachingAsyncRedisDbProxy, MonitoringAsyncRedisDbProxy
):
    pass


class CachedSettingsDict(MutableMapping):
    """Dictionary of BaseSettings that are cached. This is used so that
    the associated Redis keys are removed from the cache when the setting
    is removed from CachedSettingsDict.
    """

    def __init__(self, db_cache):
        self._cached_settings = weakref.WeakKeyDictionary()
        self.db_cache = db_cache

    def __setitem__(self, key, value):
        self._cached_settings[key] = value

    def __getitem__(self, key):
        return self._cached_settings[key]

    def __delitem__(self, key):
        name, _ = self._cached_settings[key]
        del self._cached_settings[key]
        try:
            self.db_cache.pop(name, None)
        except redis_caching.RedisCacheError:
            pass  # Not cached anyway

    def __iter__(self):
        return iter(self._cached_settings)

    def __len__(self):
        return len(self._cached_settings)


def lock_proxy(method):
    """To protect the proxy from concurrent access.
    """

    @wraps(method)
    def _lock_proxy(self, *args, **kwargs):
        with self._caching_lock:
            return method(self, *args, **kwargs)

    return _lock_proxy


def assert_tracking(method):
    """Raise exception when we cannot use the tracking connection.
    """

    @wraps(method)
    def _assert_tracking(self, *args, **kwargs):
        if not self._use_tracking_connection():
            raise redis_caching.RedisCacheError(
                f"{repr(method)} can only be executed when we are allowed to use the tracking connection"
            )
        return method(self, *args, **kwargs)

    return _assert_tracking


def caching_command(method):
    """This waits until we are allowed to use the tracking connection
    and prevents other greenlets from using that connection until we
    are done with it.

    When caching is disabled however, we will not use the tracking
    connection (in fact their is None). As a result we will executed
    the Redis command non-cached over a Connection it gets from the
    Redis connection pool.
    """

    @wraps(method)
    def _caching_command(self, *args, **kw):
        if self._use_caching:
            with self._caching_lock:
                return method(self, *args, **kw)
        else:
            # WARNING: this only works for the current inheritance structure.
            # If you derive a class from CachingRedisDbProxy it will not work.
            parent_method = getattr(super(CachingRedisDbProxy, self), method.__name__)
            return parent_method(*args, **kw)

    return _caching_command


class CachingRedisDbProxy(RedisDbProxyBase):
    """Setting/getting Redis keys through this proxy will cache them in
    the connection pool's cache.

    When settings are registered with `add_prefetch`, they will be fetched
    when they are missing from the cache. It is not required to have those
    settings cached however. It just refetches whenever invalidated due
    to changes in the Redis database.

    This could be done only if Redis version >= 6.
    """

    TYPE = enum.Enum("TYPE", "HASH KEY QUEUE ZSET")

    def __init__(self, connection_pool=None, **kw):
        self.db_cache = redis_caching.RedisCache(connection_pool=connection_pool)
        self._caching_lock = gevent.lock.RLock()
        self._enable_caching = True
        self._cached_settings = CachedSettingsDict(self.db_cache)
        kw.setdefault("async_class", CachingAsyncRedisDbProxy)
        kw.setdefault("monitoring_async_class", MonitoringCachingAsyncRedisDbProxy)
        super().__init__(connection_pool=connection_pool, **kw)
        self.enable_caching()

    def pipeline(self, **kw):
        kw.setdefault("root_proxy", self)
        return super().pipeline(**kw)

    def rotating_pipeline(self, **kw):
        kw.setdefault("root_proxy", self)
        return super().rotating_pipeline(**kw)

    def _use_tracking_connection(self):
        return self._caching_lock._is_owned()

    @property
    def connection(self):
        """Use the caching connection when RedisCache is connected and
        when we hold the proxy lock.
        """
        if self._use_tracking_connection():
            # Returns None when cache is disabled
            return self.db_cache.connection
        else:
            # A connection will be taken from the pool
            return None

    @connection.setter
    def connection(self, value):
        # This proxy should never own a connection
        pass

    def close(self):
        self.disable_caching()

    @property
    def _use_caching(self):
        return self._enable_caching

    @lock_proxy
    def disable_caching(self):
        """After this command, the proxy behaves like `RedisDbProxy`.
        All pre-fetched objects will be removed.
        """
        self._enable_caching = False
        self.clear_all_prefetch()
        self.db_cache.disconnect()

    @lock_proxy
    def enable_caching(self):
        self._enable_caching = True
        self.db_cache.connect()

    @lock_proxy
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

    @lock_proxy
    def remove_prefetch(self, *objects):
        for obj in objects:
            self._cached_settings.pop(obj, None)

    @lock_proxy
    def clear_all_prefetch(self):
        self._cached_settings.clear()

    @caching_command
    def evalsha(self, script_name, n, *args):
        keys = args[:n]
        super().evalsha(script_name, n, *args)
        # invalidate cache for those keys
        for k in keys:
            self.db_cache.pop(k, None)

    @caching_command
    def delete(self, name):
        self.db_cache.pop(name, None)
        super().delete(name)

    # KEY
    @caching_command
    def get(self, name):
        return self._get_cache_key(name)

    @caching_command
    def set(self, name, value, ex=None, px=None, nx=False, xx=False):
        return_val = super().set(name, value, ex, px, nx, xx)
        self.db_cache[name] = value
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
    def hset(self, name, *key_value_list_or_mapping, mapping=None):
        if mapping is None:
            mapping = key_value_list_or_mapping_to_dict(key_value_list_or_mapping)
        cached_dict = self._get_cache_dict(name)
        for key, value in mapping.items():
            cached_dict[key.encode()] = value

        return super().hset(name, mapping=mapping)

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
            self.db_cache.pop(name, None)

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

    @assert_tracking
    def _get_cache_dict(self, name):
        cached_dict = self.db_cache.get(name)
        if cached_dict is None:
            cached_dict = self._fill_cache(name, self.TYPE.HASH)
        return cached_dict

    @assert_tracking
    def _get_cache_key(self, name):
        value = self.db_cache.get(name)
        if value is None and name not in self.db_cache:
            value = self._fill_cache(name, self.TYPE.KEY)
        return value

    @assert_tracking
    def _get_cache_list(self, name):
        values = self.db_cache.get(name)
        if values is None:
            values = self._fill_cache(name, self.TYPE.QUEUE)
        return values

    @assert_tracking
    def _get_cache_sorted_set(self, name):
        values = self.db_cache.get(name)
        if values is None:
            # return a list with name and score
            # change it to dict
            values = dict(self._fill_cache(name, self.TYPE.ZSET))
            self.db_cache[name] = values
        return values

    @assert_tracking
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
        fetch_names.update(cached_settings.keys() - self.db_cache.keys())

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
            self.db_cache[obj_name] = result

        # Return the value of the key we actually asked for
        return self.db_cache[name]
