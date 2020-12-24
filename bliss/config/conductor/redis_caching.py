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
from contextlib import ExitStack, contextmanager
from collections.abc import MutableMapping
import redis.exceptions


"""Implementation of a client-side Redis cache with invalidation connection.
"""


class RedisCacheError(RuntimeError):
    pass


class RedisTrackingError(RuntimeError):
    pass


class CachingConnectionGreenlet(gevent.Greenlet):
    """A greenlet that holds two Redis connections from the pool:
        - one for get/set Redis keys with client-side cache
        - one for invalidation the cache when other connections
          modified those keys

    When the invalidation connection tried to reconnect, the caching
    connection is disconnected and returns too the pool.

    The RedisDbConnectionPool will reject releasing the caching connection,
    except when done by thos greenlet.
    """

    _REDIS_INVALIDATION_KEY = b"__redis__:invalidate"

    def __init__(self, db_cache, started_event):
        self._db_cache = db_cache
        self._started_event = started_event
        self._tracking_redirect_id = None
        self.connection = None
        self._close_pipe = None
        super().__init__()

    def stop(self):
        """Like `kill` but through the closing pipe. It does not raise
        an exception on timeout.

        Calling `kill` might not return the pubsub connection to the pool.
        """
        self._send_fd(self._close_pipe, b"X")

    def _run(self):
        with ExitStack() as stack:
            ctx = self._setup_close_pipe()
            rp, stop_callback = stack.enter_context(ctx)

            ctx = self._setup_invalidation_connection(stop_callback)
            pubsub = stack.enter_context(ctx)

            ctx = self._setup_tracking_connection()
            stack.enter_context(ctx)

            with self._db_cache._connection_context():
                self._started_event.set()
                self._invalidation_loop(pubsub, rp)

    @contextmanager
    def _setup_close_pipe(self):
        rp, wp = os.pipe()

        def stop_callback(*args, **kw):
            try:
                os.close(wp)
            except OSError:
                # already closed
                pass

        try:
            self._close_pipe = wp
            yield rp, stop_callback
        finally:
            self._close_pipe = None
            self._close_fd(wp)
            self._close_fd(rp)

    @staticmethod
    def _close_fd(fd):
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            # already closed
            pass

    @staticmethod
    def _send_fd(fd, msg):
        if fd is None:
            return
        try:
            os.write(fd, msg)
        except OSError:
            # already closed
            pass

    @contextmanager
    def _setup_invalidation_connection(self, stop_callback):
        pubsub = None
        try:
            pubsub, client_id = self._create_invalidation_connection(stop_callback)
            self._tracking_redirect_id = client_id
            yield pubsub
        finally:
            self._tracking_redirect_id = None
            if pubsub is not None:
                pubsub.close()

    @contextmanager
    def _setup_tracking_connection(self):
        connection = None
        try:
            self.connection = connection = self._create_tracking_connection()
            yield
        finally:
            self.connection = None
            if connection is not None:
                # Ongoing connections will get an exception (e.g. Bad file descriptor)
                # CachingRedisDbProxy has a lock to prevent having a
                # connection and closing this greenlet at the same time.
                self._stop_tracking(connection)
                self._connection_pool.release(connection)

    @property
    def _connection_pool(self):
        return self._db_cache._connection_pool

    def _create_invalidation_connection(self, stop_callback):
        """We need to maintain a single connection (so a fixed client id)
        which subscribes to invalidation messages send to the Redis
        invalidation key `__redis__:invalidate`.
        """
        proxy = self._connection_pool.create_proxy(single_connection=True)
        client_id = proxy.client_id()
        pubsub = proxy.pubsub()

        # We no longer need the proxy. Make sure it does not return
        # its connection too the connection pool.
        connection = proxy.connection
        proxy.connection = None

        # Set the pubsub connection. Instead of registering `pubsub.on_connect`,
        # which is what PubSub.execute_command normally does, we register
        # the stop callback.
        pubsub.connection = connection
        connection.register_connect_callback(stop_callback)

        pubsub.subscribe(self._REDIS_INVALIDATION_KEY)
        confirmation = pubsub.get_message(timeout=5)
        assert confirmation["type"] == "subscribe"
        assert confirmation["data"] == 1

        return pubsub, client_id

    def _create_tracking_connection(self):
        connection = self._connection_pool.get_connection(None)
        # Make sure the connection pool does not accept this connection
        connection.can_be_released = False
        self._start_tracking(connection)
        connection.register_connect_callback(self._start_tracking)
        return connection

    def _invalidation_loop(self, pubsub, rp):
        """This loop stops when the pipe or the connection is closed,
        or when trying to access the cache when it is not connected.
        """
        read_fds = [pubsub.connection._sock, rp]
        while True:
            try:
                # Returns immediately
                msg = pubsub.get_message()
            except redis.exceptions.ConnectionError:
                break

            if msg is None:
                try:
                    read_event, _, _ = gevent.select.select(read_fds, [], [])
                except ValueError:
                    # One of the sockets was closed (file descriptor -1)
                    break
                except OSError:
                    # One of the sockets was closed (bad file descriptor)
                    break
                if rp in read_event:
                    # Request for termination through the pipe
                    break
                # There is a new pubsub message
                continue

            if msg.get("channel") != self._REDIS_INVALIDATION_KEY:
                continue

            # The message is an invalidation event
            inv_keys = msg.get("data")
            if inv_keys is None:
                continue
            elif not isinstance(inv_keys, list):
                inv_keys = [inv_keys]

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

    def _start_tracking(self, connection):
        """
        :param redis.connection.Connection connection:
        """
        if not self._tracking_redirect_id:
            raise RedisCacheError("Redis key invalidation greenlet is not running")
        self._send_tracking_command(
            connection,
            "CLIENT",
            "TRACKING",
            "on",
            "REDIRECT",
            self._tracking_redirect_id,
            "BCAST",
            "NOLOOP",
        )

    def _stop_tracking(self, connection):
        """
        :param redis.connection.Connection connection:
        """
        # In analogy with `redis.client.Pipeline.reset`
        try:
            self._send_tracking_command(connection, "CLIENT", "TRACKING", "off")
        except Exception:
            connection.disconnect()
        connection.clear_connect_callbacks()
        # Make sure the connection pool accepts this connection
        connection.can_be_released = True

    @staticmethod
    def _send_tracking_command(connection, *args):
        connection.send_command(*args)
        try:
            response = connection.read_response()
        except redis.exceptions.ConnectionError:
            raise RedisTrackingError("Redis tracking command failed")
        if response != b"OK":
            raise RedisTrackingError(
                f"Redis tracking command failed (response={response})"
            )


def check_connected(method):
    """Raises `RedisCacheError` when the cache is not connected
    """

    @wraps(method)
    def _check_connected(self, *args, **kw):
        if not self.connected:
            raise RedisCacheError(f"Not connected or connection was lost: {repr(self)}")
        return method(self, *args, **kw)

    return _check_connected


class RedisCache(MutableMapping):
    """Redis cache with a mutable mapping interface, which raises
    RedisCacheError when the Redis connection is not established.

    This class is NOT greenlet-safe. Protection is currently provided
    by the CachingRedisDbProxy that owns the cache.
    """

    def __init__(self, connection_pool):
        if connection_pool is None:
            raise ValueError("connection_pool not provided")
        self._connection_pool = connection_pool
        self._cache = None
        self._connection_greenlet = None
        super().__init__()

    def __repr__(self):
        if self.connected:
            state = "CONNECTED"
        else:
            state = "CLOSED"
        return f"{super().__repr__()}<{state}: {repr(self._connection_greenlet)}>"

    @property
    def connected(self):
        """Connected means we are inside the connection context, which
        is only the case when the Redis key invalidation loop is running.
        """
        return self._cache is not None

    def connect(self, timeout=None):
        if not self.connected:
            self._stop_connection_greenlet(timeout=timeout)
            self._start_connection_greenlet(timeout=timeout)

    def disconnect(self, timeout=None):
        self._stop_connection_greenlet(timeout=timeout)

    @property
    def connection(self):
        """The connection which Redis keys will be cached and invalidated.
        Returns None when not connected.

        This connection is NOT greenlet-safe.

        You can disconnect this connection like any other Connection.
        It will reconnect when used again.
        """
        if self.connected:
            return self._connection_greenlet.connection
        else:
            return None

    @contextmanager
    def _connection_context(self):
        self._cache = dict()
        try:
            yield
        finally:
            # Ongoing operations will get a RedisCacheError exception
            self._cache = None

    def _start_connection_greenlet(self, timeout=None):
        started_event = gevent.event.Event()
        glt = CachingConnectionGreenlet(self, started_event)
        try:
            with gevent.Timeout(timeout):
                glt.start()
                started_event.wait()
                self._connection_greenlet = glt
        except gevent.Timeout:
            try:
                glt.get(timeout=0)
            except gevent.Timeout:
                # started_event not set yet
                raise RedisCacheError("Timeout establishing the Redis connections")
            except Exception:
                # Greenlet failed
                raise RedisCacheError("Failed to establish the Redis connections")
            # Greenlet finished without exception
            raise RedisCacheError("Failed to establish the Redis connections")

    def _stop_connection_greenlet(self, timeout=None):
        if not self._connection_greenlet:
            self._connection_greenlet = None
            return
        try:
            with gevent.Timeout(timeout):
                self._connection_greenlet.stop()
                self._connection_greenlet.join(timeout=10)
                # This may cause Redis connection and file descriptor leaks
                if self._connection_greenlet:
                    self._connection_greenlet.kill()
                    self._connection_greenlet.join()
        except gevent.Timeout:
            pass
        if self._connection_greenlet:
            raise RedisCacheError("Failed to close the Redis connections")
        self._connection_greenlet = None

    @check_connected
    def __setitem__(self, key, value):
        self._cache[key] = value

    @check_connected
    def __getitem__(self, key):
        return self._cache[key]

    @check_connected
    def __delitem__(self, key):
        del self._cache[key]

    @check_connected
    def __iter__(self):
        return iter(self._cache)

    @check_connected
    def __len__(self):
        return len(self._cache)
