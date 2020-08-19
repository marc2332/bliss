# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import enum
import weakref
import fnmatch
import redis
import gevent
from functools import wraps
from collections.abc import MutableMapping

from bliss.data import node
from bliss.config.conductor import client
from bliss.config import settings

_CONNECTION_CACHE = dict()
_CONNECTION_LOCK = gevent.lock.RLock()


def get_redis_client_cache(db=0):
    """
    This function return global client cache connection
    """
    with _CONNECTION_LOCK:
        cnx = _CONNECTION_CACHE.get(db)
        if cnx is None:
            base_connection = client.get_redis_connection(db=db)
            cnx = CacheConnection(base_connection)
            _CONNECTION_CACHE[db] = cnx
        return cnx


def close_all_client_cache():
    for cnx in _CONNECTION_CACHE.values():
        cnx.close()
    _CONNECTION_CACHE.clear()


def auto_connect(func):
    @wraps(func)
    def f(self, *args, **kwargs):
        with self._lock:
            self.open()
            if self._able_to_cache:
                return func(self, *args, **kwargs)

        func_base = getattr(self._base_cnx, func.__name__)
        return func_base(*args, **kwargs)

    return f


def synchronized(func):
    @wraps(func)
    def f(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)

    return f


class _PrefetchDict(MutableMapping):
    def __init__(self, cache):
        self._prefetched_objs = weakref.WeakKeyDictionary()
        self._cache = weakref.proxy(cache)

    def __setitem__(self, key, value):
        self._prefetched_objs[key] = value

    def __getitem__(self, key):
        return self._prefetched_objs[key]

    def __delitem__(self, key):
        name, _ = self._prefetched_objs[key]
        del self._prefetched_objs[key]
        self._cache._cache_values.pop(name, None)

    def __iter__(self):
        return iter(self._prefetched_objs)

    def __len__(self):
        return len(self._prefetched_objs)


class CacheConnection:
    """
    This object cache value for settings locally.
    This could be done only if Redis version >= 6.
    """

    TYPE = enum.Enum("TYPE", "HASH KEY QUEUE ZSET")

    def __init__(self, cnx):
        self._base_cnx = cnx
        self._cnx = None
        self._lock = gevent.lock.RLock()
        self._listen_task = None
        self._db = cnx.connection_pool.connection_kwargs["db"]
        # None == not initialized
        self._able_to_cache = None
        self._cache_values = dict()
        self._prefetch_objects = _PrefetchDict(self)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self._base_cnx, name)

    def __del__(self):
        self.close()

    def close(self):
        if self._listen_task:
            self._listen_task.kill()

    def disable_caching(self):
        """
        After this command, the connection behave like a standard connection.

        This will removed all the pre-fetched object and clear the cache
        """
        self._able_to_cache = False
        self.close()
        self.clear_all_prefetch()

    def open(self):
        if self._cnx is None and self._able_to_cache is not False:
            inv_client = client.get_redis_connection(
                db=self._db, single_connection_client=True, pool_name="CLIENT_CACHE"
            )
            # just need to create a connection to get the client_id
            # this connection will never use apart for this
            # this connection will be set in the pubsub.
            cnx = client.get_redis_connection(
                db=self._db, single_connection_client=True, pool_name="CLIENT_CACHE"
            )
            client_id = inv_client.client_id()
            try:
                cnx.execute_command(
                    "CLIENT", "TRACKING", "on", "REDIRECT", client_id, "BCAST", "NOLOOP"
                )
            except redis.ResponseError:
                self._able_to_cache = False
                inv_client.close()
                cnx.close()
            else:
                self._able_to_cache = True
                pubsub = inv_client.pubsub()
                # need to have the same client_id
                # exchange it with the connection that have
                # request the **client_id**.
                # The connection will be release by the pubsub.
                # so set it to None.
                pubsub.connection = inv_client.connection
                inv_client.connection = None

                pubsub.subscribe("redis:invalidate")
                listen_task = gevent.spawn(self._listen, pubsub)

                def local_kill(*args):
                    listen_task.kill(block=False)

                pubsub.connection.register_connect_callback(local_kill)
                self._cnx = cnx
                self._listen_task = listen_task

    def add_prefetch(self, *objects):
        """
        Adds object to be pre-fetched in block in case of any cache failed.
        Objects will be always kept in memory even if it is not accessed.

        Any setting can be added to be pre-fetched.
        """
        for obj in objects:
            name = obj.name
            if isinstance(obj, settings.SimpleSetting):
                self._prefetch_objects[obj] = (name, self.TYPE.KEY)
            elif isinstance(obj, settings.BaseHashSetting):
                self._prefetch_objects[obj] = (name, self.TYPE.HASH)
            elif isinstance(obj, node.DataNode):
                # pre-fetch only the internal **struct** and **info**
                # need to be symmetric with **remove_prefetch**
                struct = obj._struct
                self._prefetch_objects[struct._proxy] = (
                    struct._proxy.name,
                    self.TYPE.HASH,
                )
                self._prefetch_objects[obj.info] = (obj.info.name, self.TYPE.HASH)
            else:
                raise ValueError(f"Type not yet managed {obj}")

    def remove_prefetch(self, *objects):
        for obj in objects:
            if isinstance(obj, node.DataNode):
                struct = obj._struct
                self._prefetch_objects.pop(struct._proxy, None)
                self._prefetch_objects.pop(obj.info, None)
            else:
                self._prefetch_objects.pop(obj, None)

    def clear_all_prefetch(self):
        self._prefetch_objects.clear()

    def pipeline(self):
        # invalidate all cache
        self._cache_values.clear()
        return self._base_cnx.pipeline()

    @auto_connect
    def evalsha(self, script_name, n, *args):
        keys = args[:n]
        self._base_cnx.evalsha(script_name, n, *args)
        # invalidate cache for those keys
        for k in keys:
            self._cache_values.pop(k, None)

    # KEY
    @auto_connect
    def get(self, name):
        return self._get_cache_key(name)

    @auto_connect
    def set(self, name, value, ex=None, px=None, nx=False, xx=False):
        return_val = self._cnx.set(name, value, ex, px, nx, xx)
        self._cache_values[name] = value
        return return_val

    # HASH
    @auto_connect
    def hdel(self, name, *keys):
        return_val = self._cnx.hdel(name, *keys)
        cached_dict = self._get_cache_dict(name)
        for k in keys:
            cached_dict.pop(k.encode(), None)
        return return_val

    @auto_connect
    def hexists(self, name, key):
        cached_dict = self._get_cache_dict(name)
        return key.encode() in cached_dict

    @auto_connect
    def hget(self, name, key):
        cached_dict = self._get_cache_dict(name)
        return cached_dict.get(key.encode() if isinstance(key, str) else key)

    @auto_connect
    def hgetall(self, name):
        return self._get_cache_dict(name)

    @auto_connect
    def hlen(self, name):
        cached_dict = self._get_cache_dict(name)
        return len(cached_dict)

    @auto_connect
    def hset(self, name, key, value):
        return_val = self._cnx.hset(name, key, value)
        cached_dict = self._get_cache_dict(name)
        cached_dict[key.encode()] = value
        return return_val

    @auto_connect
    def hmset(self, name, mapping):
        return_val = self._cnx.hmset(name, mapping)
        cached_dict = self._get_cache_dict(name)
        cached_dict.update((k.encode(), v) for k, v in mapping.items())
        return return_val

    @auto_connect
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
    @auto_connect
    def lindex(self, name, index):
        cache_list = self._get_cache_list(name)
        return cache_list[index]

    @auto_connect
    def llen(self, name):
        cache_list = self._get_cache_list(name)
        return len(cache_list)

    @auto_connect
    def lpop(self, name):
        return_val = self._cnx.lpop(name)
        cache_list = self._get_cache_list(name)
        if cache_list and return_val == cache_list[0]:
            cache_list.pop(0)
        return return_val

    @auto_connect
    def lpush(self, name, *values):
        return_val = self._cnx.lpush(name, *values)
        cache_list = self._get_cache_list(name)
        for v in values:
            cache_list.insert(0, v)
        return return_val

    @auto_connect
    def lrange(self, name, start, end):
        cache_list = self._get_cache_list(name)
        if end == -1:
            end = len(cache_list)
        else:
            end += 1
        return cache_list[start:end]

    @auto_connect
    def rpop(self, name):
        return_val = self._cnx.rpop(name)
        cache_list = self._get_cache_list(name)
        if cache_list and return_val == cache_list[-1]:
            cache_list.pop(-1)
        return return_val

    # SORTED SET COMMANDS
    @auto_connect
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
        cached_dict = self._cache_values.get(name)
        if cached_dict is None:
            cached_dict = self._fill_cache(name, self.TYPE.HASH)
        return cached_dict

    def _get_cache_key(self, name):
        value = self._cache_values.get(name)
        if value is None and name not in self._cache_values:
            value = self._fill_cache(name, self.TYPE.KEY)
        return value

    def _get_cache_list(self, name):
        values = self._cache_values.get(name)
        if values is None:
            values = self._fill_cache(name, self.TYPE.QUEUE)
        return values

    def _get_cache_sorted_set(self, name):
        values = self._cache_values.get(name)
        if values is None:
            # return a list with name and score
            # change it to dict
            values = dict(self._fill_cache(name, self.TYPE.ZSET))
            self._cache_values[name] = values
        return values

    @synchronized
    def _fill_cache(self, name, object_type):
        prefetch_obj = {name: object_type}
        prefetch_obj.update(
            {name: obj_type for name, obj_type in self._prefetch_objects.values()}
        )
        needed_prefetch_name = {name}
        needed_prefetch_name.update(prefetch_obj.keys() - self._cache_values.keys())
        pipeline = self._base_cnx.pipeline()
        for obj_name in needed_prefetch_name:
            obj_type = prefetch_obj[obj_name]
            if obj_type == self.TYPE.HASH:
                pipeline.hgetall(obj_name)
            elif obj_type == self.TYPE.KEY:
                pipeline.get(obj_name)
            elif obj_type == self.TYPE.QUEUE:
                pipeline.lrange(obj_name, 0, -1)
            elif obj_type == self.TYPE.ZSET:
                pipeline.zrange(obj_name, 0, -1, withscores=True)
        ### next lines are copied from redis-py
        conn = pipeline.connection
        if not conn:
            conn = pipeline.connection_pool.get_connection("MULTI", pipeline.shard_hint)
            pipeline.connection = conn
        ###
        pipeline_result = pipeline._execute_transaction(
            conn, pipeline.command_stack, True
        )
        for obj_name, result in zip(needed_prefetch_name, pipeline_result):
            self._cache_values[obj_name] = result
        return self._cache_values[name]

    def _listen(self, pubsub):
        try:
            for msg in pubsub.listen():
                if msg.get("channel") == b"__redis__:invalidate":
                    inv_names = msg.get("data")
                    for inv_name in inv_names:
                        try:
                            self._cache_values.pop(inv_name.decode(), None)
                        except UnicodeDecodeError:
                            pass
        finally:
            with self._lock:
                cnx = self._cnx
                self._cnx = None
                self._cache_values = dict()
                pubsub.close()
                cnx.close()
