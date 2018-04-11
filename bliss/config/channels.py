# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .conductor import client
from collections import namedtuple, Counter
from functools import partial
import cPickle
import gevent
import gevent.event
import time
from bliss.common.utils import grouped
from bliss.common.event import saferef
from bliss.common.utils import OrderedDict
import weakref
import sys
import os

BUS = dict()


class ValueQuery(object):
    def __init__(self):
        pass


class NotInitialized(object):
    def __repr__(self):
        return "NotInitialized"

    def __eq__(self, other):
        if isinstance(other, NotInitialized):
            return True
        return False


_ChannelValue = namedtuple("_ChannelValue", ['timestamp', 'value'])


class _Bus(object):
    def __init__(self, redis):
        self._redis = redis
        self._pubsub = redis.pubsub()
        self._pending_subscribe = list()
        self._pending_unsubscribe = list()
        self._pending_channel_value = OrderedDict()
        self._send_event = gevent.event.Event()
        self._in_recv = set()

        self._listen_task = None
        self._send_task = gevent.spawn(self._send)

        self.channels = weakref.WeakValueDictionary()

    def subscribe(self, channel):
        self.channels[channel.name] = channel
        self._send_event.set()

    def _set_channel_value(self, channel, value):
        name = channel.name
        channel._set_raw_value(value)
        try:
            self._in_recv.add(name)
            self._fire_notification_callbacks(channel)
        finally:
            self._in_recv.remove(name)

    def update_channel(self, channel, value):
        name = channel.name
        if isinstance(value, _ChannelValue):
            # update comes from the network
            prev_channel_value = channel._get_raw_value()
            if prev_channel_value is None or \
               prev_channel_value.timestamp < value.timestamp:
                channel_value = value
            else:
                return          # already up-to-date
            self._set_channel_value(channel, channel_value)
        else:
            # update comes from channel.value assignment
            if name in self._in_recv:
                raise RuntimeError(
                    "Channel %s: detected value changed in callback" % name)
            else:
                channel_value = _ChannelValue(time.time(), value)
                self._set_channel_value(channel, channel_value)
                # inform others about the new value
                self._pending_channel_value[name] = channel_value
                self._send_event.set()

    def _fire_notification_callbacks(self, channel):
        value = channel._get_raw_value().value
        callbacks = channel._callbacks
        deleted_cb = set()
        for cb_ref in callbacks:
            cb = cb_ref()
            if cb is not None:
                try:
                    cb(value)
                except:
                    # display exception, but do not stop
                    # executing callbacks
                    sys.excepthook(*sys.exc_info())
            else:
                deleted_cb.add(cb_ref)
        callbacks.difference_update(deleted_cb)

    def init_channels(self, *channel_names):
        result = self._redis.execute_command(
            'pubsub', 'numsub', *channel_names)
        no_listener_4_values = set(
            (name for name, nb_listener in grouped(result, 2) if int(nb_listener) == 0))
        pipeline = self._redis.pipeline()
        for channel_name in channel_names:
            try:
                channel = self.channels[channel_name]
            except KeyError:
                continue
            else:
                if channel._get_raw_value() is None:
                    if channel_name in no_listener_4_values:
                        channel_value = _ChannelValue(
                            time.time(), channel.default_value)
                        self._set_channel_value(channel, channel_value)
                    else:
                        pipeline.publish(channel_name, cPickle.dumps(
                            ValueQuery(), protocol=-1))
        pipeline.execute()

    def _send(self):
        while(1):
            self._send_event.wait()
            self._send_event.clear()

            pubsub = self._pubsub
            current_channels = self.channels.keys()
            pending_subscribe = set(current_channels)-set(pubsub.channels)
            pending_unsubscribe = set(pubsub.channels)-set(current_channels)

            pending_channel_value = self._pending_channel_value
            self._pending_channel_value = OrderedDict()

            if pending_unsubscribe:
                pubsub.unsubscribe(pending_unsubscribe)

            if pending_subscribe:
                pubsub.subscribe(pending_subscribe)
                self.init_channels(*pending_subscribe)

                if self._listen_task is None or self._listen_task.ready():
                    self._listen_task = gevent.spawn(self._listen)

            if pending_channel_value:
                pipeline = self._redis.pipeline()
                for name, channel_value in pending_channel_value.iteritems():
                    try:
                        pipeline.publish(name, cPickle.dumps(
                            channel_value, protocol=-1))
                    except cPickle.PicklingError:
                        exctype, value, traceback = sys.exc_info()
                        message = "Cannot pickle channel <%s> %r with values <%r>" % \
                            (name, type(channel_value.value), channel_value.value)
                        sys.excepthook(exctype, message, traceback)
                pipeline.execute()

    def _listen(self):
        for event in self._pubsub.listen():
            event_type = event.get('type')
            if event_type == 'message':
                value = cPickle.loads(event.get('data'))
                channel_name = event.get('channel')
                try:
                    channel = self.channels[channel_name]
                except KeyError:
                    continue
                else:
                    try:
                        if isinstance(value, ValueQuery):
                            channel_value = channel._get_raw_value()
                            if channel_value is not None:
                                self._pending_channel_value[channel_name] = channel_value
                                self._send_event.set()
                            else:
                                # our channel has no value
                                pass
                        else:
                            self.update_channel(channel, value)
                    finally:
                        del channel


def Bus(redis):
    try:
        return BUS[redis]
    except KeyError:
        bus = _Bus(redis)
        BUS[redis] = bus
        return bus


class _Channel(object):
    def __init__(self, bus, name, default_value, value):
        self.__bus = bus
        self.__name = name
        self.__timeout = 3.
        self.__default_value = default_value
        self.__raw_value = None
        self._callbacks = set()
        self._value_event = gevent.event.Event()

        bus.subscribe(self)

    @property
    def name(self):
        return self.__name

    @property
    def default_value(self):
        return self.__default_value

    @property
    def value(self):
        value = self.__raw_value
        if value is None:
            # ask value
            self.__bus.init_channels(self.name)
            with gevent.Timeout(self.__timeout, RuntimeError("%s: timeout to receive channel value" % self.__name)):
                self._value_event.wait()
                self._value_event.clear()
                value = self.__raw_value
        return value.value

    @value.setter
    def value(self, new_value):
        self.__bus.update_channel(self, new_value)

    def _set_raw_value(self, value):
        self.__raw_value = value
        self._value_event.set()

    def _get_raw_value(self):
        return self.__raw_value

    @property
    def timeout(self):
        return self.__timeout

    @timeout.setter
    def timeout(self, value):
        self.__timeout = value

    def register_callback(self, callback):
        if callable(callback):
            cb_ref = saferef.safe_ref(callback)
            self._callbacks.add(cb_ref)
        else:
            raise ValueError("Channel %s: %r is not callable",
                             self.name, callback)

    def unregister_callback(self, callback):
        cb_ref = saferef.safe_ref(callback)
        try:
            self._callbacks.remove(cb_ref)
        except KeyError:
            pass

    def __repr__(self):
        self.value
        return '%s->%s' % (self.__name, self.__raw_value)


def Channel(name, value=NotInitialized(), callback=None,
            default_value=None, redis=None):
    if redis is None:
        redis = client.get_cache()

    bus = Bus(redis)

    try:
        chan = bus.channels[name]
    except KeyError:
        chan = _Channel(bus, name, default_value, value)

    if not isinstance(value, NotInitialized):
        chan.value = value

    if callback is not None:
        chan.register_callback(callback)

    return chan


DEVICE_CACHE = weakref.WeakKeyDictionary()


def Cache(device, key, **keys):
    """
    Create a cache value for a device. Device object must have a *name* in his attributes.
    This class should be used to optimized the device access.
    i.e: Don't re-configure a device if it's already configured
    """
    try:
        device_name = device.name
    except AttributeError:
        raise RuntimeError(
            "cache: can't create a cache value (%s), the device (%s) has no name" % (device, key))

    default_value = keys.get('default_value', None)
    cached_channels = DEVICE_CACHE.setdefault(device, dict())
    key_name = '%s:%s' % (device.name, key)
    cached_channels[key_name] = default_value
    return Channel(key_name, **keys)


def clear_cache(*devices):
    """
    Clear cache for the associated devices
    devices -- one or more devices or if no device all devices
    """
    if not devices:
        devices = DEVICE_CACHE.keys()
    for d in devices:
        cached_channels = DEVICE_CACHE.get(d, dict())
        for channel_name, default_value in cached_channels.iteritems():
            chan = Channel(channel_name)
            chan.value = default_value
