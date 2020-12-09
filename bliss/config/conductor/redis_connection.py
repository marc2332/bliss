# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""This module provided the primary API on top of py-redis.

Creating a Redis connection is typically done like this:

    pool = create_connection_pool("redis://localhost:25002", db=1)
    proxy = pool.create_proxy()

The proxies provide an API to the Redis commands. For example to get all
keys in the Redis database:

    keys = proxy.keys()

These proxies are greenlet-safe and get a connection from the pool to
execute each command. They release the connection back to the pool after
receiving the result. Closing all connections can be done by disconnecting
the pool (also called on garbage collection):

    pool.disconnect()

To create proxies with client-side Redis caching, you can use:

    pool = create_connection_pool("redis://localhost:25002", db=1, caching=True)
    proxy = pool.create_proxy()

These proxies are also greenlet-safe. You will have one cache per pool.
"""


import os
import gevent
import weakref
import socket
import redis

from bliss.config.conductor import redis_proxy
from bliss.config.conductor import redis_caching


class RedisDbConnectionPool(redis.ConnectionPool):
    """Manages the connections to a particular Redis server and database.
    Instantiate this pool with the factory method `create_connection_pool`.
    Use a different pool for each database, even when on the same server.

    RedisDbConnectionPool is greenlet-safe.

    When getting a `redis.connection.Connection` from the pool it either
    returns an existing connection (and hence socket) or it tries to add
    a new connection to the pool. `ConnectionError` is raised when the
    maximal pool size is reached.

    Connections are not closed until `disconnect` is called. This method
    is also called upon garbage collection. So when `RedisDbConnectionPool`
    is destroyed, all its connections are closed, also the connections that
    are in used by proxies.

    A `redis.connection.Connection` instance is not greenlet-safe but it
    can be reused in different greenlets.

    Redis database proxies can be instantiated with `create_proxy`.
    """

    CLIENT_NAME = f"{socket.gethostname()}:{os.getpid()}"

    def __init__(self, *args, **kw):
        kw.setdefault("client_name", self.CLIENT_NAME)
        super().__init__(*args, **kw)
        # Replace thread safety with greenlet safety
        self._fork_lock = gevent.lock.RLock()

    def reset(self):
        super().reset()
        # Replace thread safety with greenlet safety
        self._lock = gevent.lock.RLock()

    def release(self, connection):
        with self._lock:
            # The proxy's `close` method could be executed concurrently,
            # thereby releasing its connection (if it has one) more than once.
            try:
                return super().release(connection)
            except KeyError:
                pass  # Already released

    def clean_pubsub(self, connection):
        # TODO: is this still used?
        with self._lock:
            connection.disconnect()
            connection.clear_connect_callbacks()
            self.release(connection)

    def create_proxy(self):
        """The pool itself does not keep a reference to this proxy
        """
        return redis_proxy.SafeRedisDbProxy(self)

    def create_single_connection_proxy(self):
        """The pool itself does not keep a reference to this proxy
        """
        return redis_proxy.SingleRedisConnectionProxy(self)


class CachingRedisDbConnectionPool(RedisDbConnectionPool):
    """Like `RedisDbConnectionPool` but it implements Redis client side
    caching. Currently the caching is done on the proxy level. In the
    future it needs to be done on the connection level and this calls
    will use a custom connection class which handles the caching.
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._enable_lock = gevent.lock.RLock()
        self._caching_enabled = False
        self.db_cache = redis_caching.RedisCache(weakref.proxy(self))
        self.enable_caching()

    def enable_caching(self, timeout=None):
        self.disconnect()
        self.db_cache.enable(timeout=timeout)
        self._caching_enabled = True

    def disable_caching(self, timeout=5):
        """Behaves like `RedisDbConnectionPool` after calling this
        """
        self.db_cache.disable(timeout=timeout)
        self._caching_enabled = False

    def make_connection(self, *args, **kw):
        """The new connection needs to send the tracking redirect command
        upon connecting to Redis.
        """
        connection = super().make_connection(*args, **kw)
        if self._caching_enabled:
            connection.register_connect_callback(self.db_cache.track_connection)
        return connection

    def disconnect(self):
        self.db_cache.disable(timeout=5)
        super().disconnect()

    def create_proxy(self):
        return redis_proxy.CachingRedisDbProxy(self)

    def create_single_connection_proxy(self):
        raise NotImplementedError

    def create_uncached_proxy(self):
        return super().create_proxy()

    def create_uncached_single_connection_proxy(self):
        return super().create_single_connection_proxy()


def create_connection_pool(
    redis_url: str, db: int, caching=False, **kw
) -> RedisDbConnectionPool:
    """This is the starting point to create Redis connections.
    """
    if caching:
        return CachingRedisDbConnectionPool.from_url(redis_url, db=db, **kw)
    else:
        return RedisDbConnectionPool.from_url(redis_url, db=db, **kw)
