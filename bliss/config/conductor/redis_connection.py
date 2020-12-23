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


class RedisDbConnectionPool(redis.ConnectionPool):
    """Manages the connections to a particular Redis server and database.
    Instantiate this pool with the factory method `create_connection_pool`.
    Use a different pool for each database, even when on the same server.

    RedisDbConnectionPool is greenlet-safe except for `disconnect`. That
    will interrupt commands executed in other greenlets. Use `safe_disconnect`
    to let ongoing commands finish and close the connection afterwards.

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
        self._closing_connections = set()

    @property
    def nconnections(self):
        return (
            len(self._in_use_connections)
            + len(self._closing_connections)
            + len(self._available_connections)
        )

    def reset(self):
        super().reset()
        # Replace thread safety with greenlet safety
        self._lock = gevent.lock.RLock()
        self._closing_connections = set()

    def clean_pubsub(self, connection):
        # TODO: is this still used?
        with self._lock:
            connection.disconnect()
            connection.clear_connect_callbacks()
            self.release(connection)

    def disconnect(self, **kw):
        """Close all connections (closes sockets, instances stay referenced).
        """
        with self._lock:
            self._in_use_connections.update(self._closing_connections)
            self._closing_connections = set()
            super().disconnect(**kw)

    def safe_disconnect(self, **kw):
        """Close unused connections. Used connections will be closed
        upon release.

        As opposed to `disconnect`, this is greenlet-safe.
        """
        with self._lock:
            self._closing_connections.update(self._in_use_connections)
            self._in_use_connections = set()
            super().disconnect(**kw)

    def make_connection(self, *args, **kw):
        connection = super().make_connection(*args, **kw)
        connection.can_be_released = True
        return connection

    def _accept_connection(self, connection):
        """This could disconnect the connection and remove its connect
        callbacks when `safe_disconnect` was called while the connection
        was used.
        """
        if not connection.can_be_released:
            # This connection is release by a proxy but still owned by
            # CacheInvalidationGreenlet.
            return False
        if connection in self._closing_connections:
            connection.disconnect()
            connection.clear_connect_callbacks()
            self._closing_connections.remove(connection)
            self._in_use_connections.add(connection)
        return True

    def release(self, connection):
        """Return back to the pool if the pool accepts it.
        """
        with self._lock:
            if not self._accept_connection(connection):
                return
            try:
                super().release(connection)
            except KeyError:
                pass

    def remove(self, connection):
        """Alternative too `release` but remove from the pool.
        """
        with self._lock:
            if not self._accept_connection(connection):
                return
            try:
                self._in_use_connections.remove(connection)
            except KeyError:
                pass

    def create_proxy(self, caching=False, single_connection=False):
        """The pool itself does not keep a reference to this proxy
        """
        if caching:
            return redis_proxy.CachingRedisDbProxy(connection_pool=self)
        elif single_connection:
            return redis_proxy.SingleConnectionRedisDbProxy(connection_pool=self)
        else:
            return redis_proxy.RedisDbProxy(connection_pool=self)

    def preconnect(self, nconnections):
        """Make sure we have already N connections in the pool
        """
        connections = [self.get_connection(None) for _ in range(nconnections)]
        for connection in connections:
            self.release(connection)


def create_connection_pool(redis_url: str, db: int, **kw) -> RedisDbConnectionPool:
    """This is the starting point to create Redis connections.
    """
    return RedisDbConnectionPool.from_url(redis_url, db=db, **kw)
