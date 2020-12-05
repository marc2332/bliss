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

If you need a proxy which holds a fixed connection during its lifetime:

   unsafe_proxy = pool.create_fixed_connection_proxy()

The connection is fetched from the pool during instantiation and will
be returned when closing the proxy (also called on garbage collection)

    unsafe_proxy.close()

These fixed-connection proxies are not greenlet-safe.
"""


import os
import socket
import gevent
import redis


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

    Database proxies can be instantiated with `create_proxy` or
    `create_fixed_connection_proxy`.
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
        return SafeRedisDbProxy(self)

    def create_fixed_connection_proxy(self):
        """The pool itself does not keep a reference to this proxy
        """
        return FixedConnectionRedisDbProxy(self)


def create_connection_pool(redis_url: str, db: int, **kw) -> RedisDbConnectionPool:
    return RedisDbConnectionPool.from_url(redis_url, db=db, **kw)


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

    The `redis.client.Pipeline` instance uses the same connection pool.
    The `redis.client.Pipeline` instance is NOT greenlet-safe.
    """

    def __init__(self, pool: RedisDbConnectionPool, **kw):
        super().__init__(connection_pool=pool, **kw)
        self.client_setname(pool.CLIENT_NAME)


class SafeRedisDbProxy(RedisDbProxy):
    """It gets a Connection from the pool every time it executes a command.
    Therefore it is greenlet-safe: each concurrent command is executed using
    a different connection.
    """

    def __init__(self, pool: RedisDbConnectionPool):
        super().__init__(pool, single_connection_client=False)


class FixedConnectionRedisDbProxy(RedisDbProxy):
    """It gets a connection from the pool during instantiation and holds that
    connection until `close` is called (called upon garbage collection).
    Since `redis.connection.Connection` is NOT greenlet-safe, neither is
    `FixedConnectionRedisDbProxy`.

    Warning: the `redis.client.Pipeline` instance gets a new connection
    from the connection pool.
    """

    def __init__(self, pool: RedisDbConnectionPool):
        super().__init__(pool, single_connection_client=True)
