# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import weakref
import gevent
import gevent.event
from functools import wraps
from collections.abc import MutableMapping


"""Implementation of a client-side Redis cache with invalidation connection.
"""


class RedisCacheError(RuntimeError):
    pass


class CacheInvalidationGreenlet(gevent.Greenlet):
    """Greenlet that subscribes to the Redis invalidation key
    """

    _REDIS_INVALIDATION_KEY = b"__redis__:invalidate"

    def __init__(self, connection_pool, db_cache, started_event):
        self._connection_pool = connection_pool
        self._db_cache = db_cache
        self._started_event = started_event
        self._tracking_redirect_id = None
        self._close_pipe_read = None
        self._close_pipe_write = None
        super().__init__()

    def kill(self):
        """Try to close through the pipe first. Kill the greenlet if that
        doesn't work.
        """
        self._close_fd(self._close_pipe_write)
        try:
            self.join(timeout=1)
        except gevent.Timeout:
            super().kill()

    def _run(self):
        try:
            pubsub = self._setup_invalidation_connection()
            self._db_cache._cache = dict()
            self._db_cache._enabled = True
            self._started_event.set()
            self._invalidation_loop(pubsub)
        finally:
            self._db_cache._enabled = False
            self._db_cache._cache = None
            self._tracking_redirect_id = None
            self._close_fd(self._close_pipe_write)
            self._close_pipe_write = None
            self._close_fd(self._close_pipe_read)
            self._close_pipe_read = None

    @staticmethod
    def _close_fd(fd):
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            # already closed
            pass

    def _setup_invalidation_connection(self):
        """We need to maintain a single connection (so a fixed client id)
        which subscribes to invalidation messages send to the Redis
        invalidation key `__redis__:invalidate`.
        """
        proxy = self._connection_pool.create_uncached_single_connection_proxy()
        tracking_redirect_id = proxy.client_id()
        pubsub = proxy.pubsub()

        # Pass the fixed connection to the PubSub instance. We no longer
        # need the proxy that held the connection. Make sure closing the
        # proxy does not give the connection back to the pool.
        pubsub.connection = proxy.connection
        proxy.connection = None
        del proxy

        pubsub.subscribe(self._REDIS_INVALIDATION_KEY)
        confirmation = pubsub.get_message(timeout=5)
        assert confirmation["type"] == "subscribe"
        assert confirmation["data"] == 1

        rp, wp = os.pipe()
        self._close_pipe_read = rp
        self._close_pipe_write = wp

        def local_kill(*args):
            try:
                os.close(wp)
            except OSError:  # pipe was already closed
                pass

        # When the pubsub connection tries to reconnect, we need to
        # stop this greenlet and invalidate the entire cache.
        pubsub.connection.register_connect_callback(local_kill)

        self._tracking_redirect_id = tracking_redirect_id
        return pubsub

    def _invalidation_loop(self, pubsub):
        """This loop is stopped when killing the greenlet or when the
        pubsub instance tries to reconnect. This means it was disconnected
        and we could have missed invalidation messages.
        """
        read_fds = [pubsub.connection._sock, self._close_pipe_read]
        while True:
            # Returns immediately
            msg = pubsub.get_message()
            if msg is None:
                read_event, _, _ = gevent.select.select(read_fds, [], [])
                if self._close_pipe_read in read_event:
                    # The connection was closed
                    break
                # There is a new pubsub message
                continue

            if msg.get("channel") != self._REDIS_INVALIDATION_KEY:
                continue

            # The message is an invalidation event
            inv_keys = msg.get("data")
            if not isinstance(inv_keys, list):
                continue

            # Invalidate local caching of these Redis keys,
            # which means remove those keys
            for key in inv_keys:
                try:
                    self._db_cache.pop(key.decode(), None)
                except (TypeError, RedisCacheError):
                    # The cache is in the process of closing down
                    #   - set to None which gives this TypeError
                    #   - disabled which gives RedisCacheError
                    break
                except UnicodeDecodeError:
                    pass

    def track_connection(self, connection):
        """Send the tracking redirect command to Redis. As a result, we
        will get invalidation messages for all keys that are get/set over
        this connection will cause the server

        :param redis.connection.Connection connection:
        """
        if not self._tracking_redirect_id:
            raise RedisCacheError("Redis key invalidation greenlet is not running")
        # Requires Redis protocol RESP3, supported by Redis 6.
        connection.send_command(
            "CLIENT",
            "TRACKING",
            "on",
            "REDIRECT",
            self._tracking_redirect_id,
            "BCAST",
            "NOLOOP",
        )
        if connection.read_response() != b"OK":
            raise RuntimeError("Cannot start Redis key invalidation tracking")


def check_enabled(method):
    """Raises `RedisCacheError` when the cache is not enabled
    """

    @wraps(method)
    def inner(self, *args, **kw):
        if not self.enabled:
            raise RedisCacheError("The Redis cache is not enabled")
        return method(self, *args, **kw)

    return inner


class RedisCache(MutableMapping):
    """Redis cache with a mutable mapping interface, which raises
    ConnectionRefusedError when not subscribed to the Redis invalidation key.
    """

    def __init__(self, connection_pool):
        self._connection_pool = connection_pool
        self._enabled = False
        # Until caching is done on the connection level:
        self.cache_lock = gevent.lock.RLock()
        self._cache = None
        self._invalidation_greenlet = None
        super().__init__()

    def __del__(self):
        self.disable()

    @property
    def enabled(self):
        return self._enabled

    @property
    def disabled(self):
        return not self.enabled

    def enable(self, timeout=None):
        """Start the invalidation greenlet and enable client tracking
        (see `track_connection`), in that order.
        """
        if self.enabled:
            return
        with gevent.Timeout(timeout):
            started_event = gevent.event.Event()
            glt = CacheInvalidationGreenlet(
                self._connection_pool, weakref.proxy(self), started_event
            )
            glt.start()
            try:
                started_event.wait()
            except gevent.Timeout:
                # Show why the greenlet did not start
                try:
                    glt.get(timeout=0)
                except gevent.Timeout:
                    pass
                # Show the original timeout error
                raise
            self._invalidation_greenlet = glt

    def disable(self):
        """Disable client tracking (see `track_connection`) and kill
        the invalidation greenlet, in that order.
        """
        self._enabled = False
        if self._invalidation_greenlet:
            self._invalidation_greenlet.kill()
        self._invalidation_greenlet = None

    @check_enabled
    def __setitem__(self, key, value):
        self._cache[key] = value

    @check_enabled
    def __getitem__(self, key):
        return self._cache[key]

    @check_enabled
    def __delitem__(self, key):
        del self._cache[key]

    @check_enabled
    def __iter__(self):
        return iter(self._cache)

    @check_enabled
    def __len__(self):
        return len(self._cache)

    def track_connection(self, connection):
        """Send the tracking redirect command to Redis.

        :param redis.connection.Connection connection:
        """
        if not self.enabled:
            # This is the invalidation pubsub connection itself
            # Or this is called by a Connection making a new connection
            # while the cache is disabled or in the process of being
            # disabled
            return
        self._invalidation_greenlet.track_connection(connection)
