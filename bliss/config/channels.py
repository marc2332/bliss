# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import uuid
import time
import cPickle
import weakref
from collections import namedtuple

import gevent
import gevent.event
import gevent.queue

from .conductor import client
from bliss.common.event import saferef


_NotProvided = type('_NotProvided', (), {})()
_Query = namedtuple('_Query', 'id')
_Reply = namedtuple('_Reply', 'id value')
_Value = namedtuple("_Value", 'timestamp value')


class AdvancedInstantiationInterface(object):
    """Base class defining a standard for advanced instanciation.

    It provides three methods to override:
    - `__new__`
    - `__preinit__`
    - `__init__`

    The __new__ and __init__ methods are called once for every access,
    i.e `cls(*args, **kwargs)`

    The `__preinit__` method is called once for every instanciation.

    It is up to `__new__` to decide whether the access should return an
    existing or a new instance. New instances are created using the
    `instanciate` method.

    Although `__new__` and `__init__` will receive the access arguments,
    `__preinit__` is free to use a different set of arguments. It is up
    to `__new__` to pass meaningful arguments to `cls.instanciate`.
    """

    def __new__(cls, *args, **kwargs):
        """Called once for every access, i.e: `cls(*args, **kwargs)`

        It should either:
        - return an existing instance
        - create an instance using cls.instanciate and return it
        """
        return cls.instanciate(*args, **kwargs)  # pragma: no cover

    def __preinit__(self, *args, **kwargs):
        """Called once for every instanciation, i.e:
        cls.instanciate(*args, **kwargs)

        It is optional and meant to initialize the internals of the instance.
        """
        pass  # pragma: no cover

    def __init__(self, *args, **kwargs):
        """Called once for every access, i.e: `cls(*args, **kwargs)`

        It is optional and meant to add extra logic to instance accesses.
        """
        pass  # pragma: no cover

    @classmethod
    def instanciate(cls, *args, **kwargs):
        """Bypass the access logic and instanciate the class directly.

        It is meant to be called within the `__new__` method.
        """
        self = object.__new__(cls)
        self.__preinit__(*args, **kwargs)
        return self


class Bus(AdvancedInstantiationInterface):

    # Instances are cached

    _CACHE = {}

    def __new__(cls, redis=None):
        if redis is None:
            redis = client.get_cache()
        if redis not in cls._CACHE:
            cls._CACHE[redis] = cls.instanciate(redis)
        return cls._CACHE[redis]

    # Initialize

    def __preinit__(self, redis):
        # Redis access
        self._redis = redis
        self._pubsub = redis.pubsub()

        # Internal structures
        self._reply_queues = {}
        self._current_subs = set()
        self._pending_updates = set()
        self._channels = weakref.WeakValueDictionary()

        # Tasks
        self._listen_task = None
        self._send_task = gevent.spawn(self._send)
        self._send_event = gevent.event.Event()

    # Close

    def close(self):
        if self._send_task:
            self._send_task.kill()
        if self._listen_task:
            self._listen_task.kill()

    @classmethod
    def clear_cache(cls):
        for bus in cls._CACHE.values():
            bus.close()
        cls._CACHE.clear()

    # Cache management

    def get_channel(self, name):
        return self._channels.get(name)

    def set_channel(self, channel):
        self._channels[channel.name] = channel
        self._send_event.set()

    # Update management

    def schedule_update(self, channel):
        self._pending_updates.add(channel)
        self._send_event.set()

    # Querying

    def query(self, name):
        # Initialize
        reply_value = None
        query_id = uuid.uuid1().hex
        reply_queue = gevent.queue.Queue()

        # Register reply queue
        self._reply_queues[query_id] = reply_queue

        # Send the query
        expected_replies = self._publish(name, _Query(query_id))

        # Loop over replies
        while expected_replies:
            reply = reply_queue.get()
            expected_replies -= 1

            # Break if a valid value is received
            if reply.value is not None:
                reply_value = reply.value
                break

        # Unregister queue
        del self._reply_queues[query_id]

        # Return value
        return reply_value

    # Publishing helper

    def _publish(self, name, value, pipeline=None):
        redis = self._redis if pipeline is None else pipeline
        return redis.publish(name, cPickle.dumps(value, protocol=-1))

    def _send_updates(self, pipeline=None):
        while self._pending_updates:
            channel = self._pending_updates.pop()
            self._publish(channel.name, channel._raw_value, pipeline)

    # Background tasks

    def _send(self):
        while True:
            # Synchronize
            self._send_event.wait()
            self._send_event.clear()

            # Initialize
            pubsub = self._pubsub
            current_channels = dict(self._channels)

            # Unsubscribe
            pending_unsubscribe = self._current_subs - set(current_channels)
            if pending_unsubscribe:
                pubsub.unsubscribe(pending_unsubscribe)
                self._current_subs -= pending_unsubscribe

            # Subscribe
            pending_subscribe = set(current_channels) - self._current_subs
            if pending_subscribe:
                pubsub.subscribe(pending_subscribe)
                self._current_subs |= pending_subscribe

            # Set subscribed events
            for name in self._current_subs:
                current_channels[name]._subscribed_event.set()

            # Make sure listen task is running
            if self._listen_task is None or self._listen_task.ready():
                self._listen_task = gevent.spawn(self._listen)

            # Create and run the pipeline of pending updates
            pipeline = self._redis.pipeline()
            self._send_updates(pipeline)
            pipeline.execute()

            # Delete channel references
            del current_channels

    def _listen(self):
        # Loop over events
        for event in self._pubsub.listen():

            # Filter events
            event_type = event.get('type')
            if event_type != 'message':
                continue

            # Extract info
            name = event.get('channel')
            data = cPickle.loads(event.get('data'))
            channel = self._channels.get(name)

            # Run the corresponding handler
            if isinstance(data, _Query):
                self._on_query(name, channel, data)
            if isinstance(data, _Reply):
                self._on_reply(name, channel, data)
            if isinstance(data, _Value):
                self._on_value(name, channel, data)

            # Delete channel reference
            del channel

    # Event handlers

    def _on_query(self, name, channel, query):
        # Reply even if the channel doesn't exist anymore
        if channel is None:
            value = None
        # Get raw value
        else:
            value = channel._raw_value
        # Reply with the corresponding query id
        reply = _Reply(query.id, value)
        self._publish(name, reply)

    def _on_reply(self, name, channel, reply):
        # Ignore replies if the id doesn't match any query id
        if reply.id not in self._reply_queues:
            return
        # Put the reply in the corresponding queue
        self._reply_queues[reply.id].put(reply)

    def _on_value(self, name, channel, value):
        # Ignore value if the channel doesn't exist anymore
        if channel is None:
            return
        # Ignore values if the channel is not ready
        if not channel.ready:
            return
        # Set the provided value
        channel._set_raw_value(value)


class Channel(AdvancedInstantiationInterface):

    # Rely on the bus to instanciate the channel

    def __new__(cls, name, *args, **kwargs):
        # Get the bus
        bus = kwargs.get('bus')
        if bus is None:
            bus = Bus(kwargs.get('redis'))

        # Get the channel
        channel = bus.get_channel(name)
        if channel is None:
            channel = cls.instanciate(bus, name)
            bus.set_channel(channel)
        return channel

    # Initialize

    def __preinit__(self, bus, name):
        # Configuration
        self._bus = bus
        self._name = name
        self._timeout = None

        # Internal values
        self._raw_value = None
        self._callback_refs = set()
        self._firing_callbacks = False
        self._default_value = None

        # Task and events
        self._query_task = None
        self._value_event = gevent.event.Event()
        self._subscribed_event = gevent.event.Event()

    def __init__(self, name,
                 value=_NotProvided,
                 default_value=_NotProvided,
                 callback=None,
                 timeout=None,
                 redis=None,
                 bus=None):
        if timeout is not None:
            self._timeout = timeout

        if default_value != _NotProvided:
            self._default_value = default_value

        if value != _NotProvided:
            self._set_raw_value(value)
            self._bus.schedule_update(self)

        if callback is not None:
            self.register_callback(callback)

        if self._raw_value is None:
            self._start_query()

    # Read-only properties

    @property
    def name(self):
        return self._name

    @property
    def default_value(self):
        return self._default_value

    @property
    def ready(self):
        return (self._value_event.is_set() and
                self._subscribed_event.is_set())

    # Timeout

    @property
    def timeout(self):
        return self._timeout or 3.

    @timeout.setter
    def timeout(self, value):
        self._timeout = value

    def wait_ready(self):
        timeout_error = RuntimeError(
            "Timeout: channel {} is not ready".format(self._name))
        with gevent.Timeout(self.timeout, timeout_error):
            self._subscribed_event.wait()
            self._value_event.wait()

    # Exposed value

    @property
    def value(self):
        self.wait_ready()
        return self._raw_value.value

    @value.setter
    def value(self, new_value):
        if self._firing_callbacks:
            raise RuntimeError(
                "Channel {}: can't set value while running a callback"
                .format(self.name))
        self.wait_ready()
        self._set_raw_value(new_value)
        self._bus.schedule_update(self)

    # Raw value

    def _set_raw_value(self, value):
        # Cast to _Value
        if not isinstance(value, _Value):
            value = _Value(time.time(), value)
        # Discard older values
        if self._raw_value is not None and \
           self._raw_value.timestamp >= value.timestamp:
            return
        # Set value and notify everyone
        self._raw_value = value
        self._value_event.set()
        self._fire_callbacks()

    # Query handling

    def _start_query(self):
        # Prevent two queries to run simultaneously
        if self._query_task is not None and not self._query_task.ready():
            return

        def query_task():
            # Wait subscription
            self._subscribed_event.wait()

            # Run the query
            reply_value = self._bus.query(self.name)

            # Use default value if necessary
            if reply_value is None:
                reply_value = self._default_value

            # Set the value
            self._set_raw_value(reply_value)

            # Unregister task if everything went smoothly
            self._query_task = None

        # Spawn the query task
        self._query_task = gevent.spawn(query_task)

    # User callbacks

    def register_callback(self, callback):
        if not callable(callback):
            raise ValueError(
                "Channel {}: {!r} is not callable".format(self.name, callback))
        cb_ref = saferef.safe_ref(callback)
        self._callback_refs.add(cb_ref)

    def unregister_callback(self, callback):
        cb_ref = saferef.safe_ref(callback)
        try:
            self._callback_refs.remove(cb_ref)
        except KeyError:
            pass

    def _fire_callbacks(self):
        value = self._raw_value.value
        callbacks = filter(None, [ref() for ref in self._callback_refs])

        # Run callbacks
        for cb in callbacks:
            # Set the flag
            try:
                self._firing_callbacks = True
                cb(value)
            # Catch and display exception
            except:
                sys.excepthook(*sys.exc_info())
            # Clean up the flag
            finally:
                self._firing_callbacks = False

        # Clean up
        self._callbacks = {
            ref for ref in self._callback_refs if ref() is not None}

    # Representation

    def __repr__(self):
        value = self._raw_value
        if value is None:
            value = '<initializing>'
        return '{}->{}'.format(self.name, value)


# Device cache

DEVICE_CACHE = weakref.WeakKeyDictionary()


def Cache(device, key, **kwargs):
    """
    Create a cache value for a device.

    Device object must have a *name* in his attributes.
    This class should be used to optimized the device access.
    i.e: Don't re-configure a device if it's already configured
    """
    try:
        device_name = device.name
    except AttributeError:
        raise TypeError(
            "Cache: can't create a cache value for key {}, "
            "the device {} has no name"
            .format(key, device))

    cached_channels = DEVICE_CACHE.setdefault(device, [])
    name = '%s:%s' % (device_name, key)
    channel = Channel(name, **kwargs)
    cached_channels.append(channel)
    return channel


def clear_cache(*devices):
    """
    Clear cache for the associated devices
    devices -- one or more devices or if no device all devices
    """
    if not devices:
        devices = DEVICE_CACHE.keys()
    for device in devices:
        cached_channels = DEVICE_CACHE.get(device, [])
        for channel in cached_channels:
            channel.value = channel.default_value
