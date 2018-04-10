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

_ChannelValue = namedtuple("_ChannelValue",['timestamp','value'])

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
    
        self.channels = dict()
        self.channel_value = dict()
        self.channel_cbk = dict()

    def subscribe(self, name, chan):
        def on_die(killed_ref):
            # the channel is removed from dict,
            # and callbacks too but *not* values
            # since another Channel may be created
            # just after, in this case it is not
            # unsubscribed and last received value is still ok
            self.channels.pop(name, None)
            self.channel_cbk.pop(name, None)
            self.unsubscribe(name)

        self.channels[name] = weakref.ref(chan, on_die)

        self._pending_subscribe.append(name)
        self._send_event.set()

    def unsubscribe(self,name):
        self._pending_unsubscribe.append(name)
        self._send_event.set()

    def _set_channel_value(self, name, value):
        self.channel_value[name] = value # synchronous set
        channel_ref = self.channels.get(name)
        if channel_ref:
            channel = channel_ref()
            if channel:
                channel._value_event.set()
                try:
                    self._in_recv.add(name)
                    self._fire_notification_callbacks(name, value.value)
                finally:
                    self._in_recv.remove(name)

    def update_channel(self,name,value):
        if isinstance(value,_ChannelValue):
            prev_channel_value = self.channel_value.get(name)
            if(prev_channel_value is None or 
               prev_channel_value.timestamp < value.timestamp):
                channel_value = value
            else:
                return          # already up-to-date
            self._set_channel_value(name, channel_value)
        else:
            channel_value = _ChannelValue(time.time(),value)

        if name not in self._in_recv:
            self._set_channel_value(name, channel_value)
            self._pending_channel_value[name] = channel_value
            self._send_event.set()
        elif not isinstance(value,_ChannelValue):
            raise RuntimeError("Channel %s: detected value changed in callback" % name)
    
    def _fire_notification_callbacks(self,name,value):
        deleted_cb = set()
        for cb_ref in self.channel_cbk.get(name,set()):
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
        self.channel_cbk.get('name',set()).difference_update(deleted_cb)

    def _send(self):
        while(1):
            self._send_event.wait()
            self._send_event.clear()
 
            #local transfer
            pending_subscribe = \
            dict(Counter(self._pending_subscribe)-Counter(self._pending_unsubscribe)).keys()
            pending_unsubscribe = \
            dict(Counter(self._pending_unsubscribe)-Counter(self._pending_subscribe)).keys()
            pending_channel_value = self._pending_channel_value
            pubsub = self._pubsub

            self._pending_subscribe = list()
            self._pending_unsubscribe = list()
            self._pending_channel_value = OrderedDict()

            if pending_unsubscribe:
                pubsub.unsubscribe(pending_unsubscribe)
                for channel_name in pending_unsubscribe:
                    # now we are really unsubscribed, remove value
                    self.channel_value.pop(channel_name, None)

            if pending_subscribe:
                result = self._redis.execute_command('pubsub','numsub',*pending_subscribe)
                no_listener_4_values = set((name for name,nb_listener in grouped(result,2) if int(nb_listener) == 0))
                pipeline = self._redis.pipeline()
                pubsub.subscribe(pending_subscribe)
                for channel_name in pending_subscribe:
                    no_listener_4_values
                    channel_ref = self.channels.get(channel_name)
                    if channel_ref:
                        channel = channel_ref()
                        if channel:
                            if channel_name not in self.channel_value:
                                if channel_name in no_listener_4_values:
                                    self._set_channel_value(channel_name,
                                                            _ChannelValue(time.time(),
                                                                          channel.default_value))
                                else:
                                    pipeline.publish(channel_name, cPickle.dumps(ValueQuery(),protocol=-1))
                            channel._subscribed_event.set()
                pipeline.execute()

                if self._listen_task is None:
                    self._listen_task = gevent.spawn(self._listen)

            if pending_channel_value:
                pipeline = self._redis.pipeline()
                for name,channel_value in pending_channel_value.iteritems():
                    try:
                        pipeline.publish(name,cPickle.dumps(channel_value,protocol=-1))
                    except cPickle.PicklingError:
                        exctype,value,traceback = sys.exc_info()
                        message = "Cannot pickle channel <%s> %r with values <%r>" % \
                        (name,type(channel_value.value),channel_value.value)
                        sys.excepthook(exctype,message,traceback)
                pipeline.execute()

    def _listen(self):
        for event in self._pubsub.listen():
            event_type = event.get('type')
            if event_type == 'message':
                value = cPickle.loads(event.get('data'))
                channel_name = event.get('channel')
                if isinstance(value,ValueQuery):
                    channel_value = self.channel_value.get(channel_name)
                    if channel_value is not None:
                        self._pending_channel_value[channel_name] = channel_value
                        self._send_event.set()
                else:
                    self.update_channel(channel_name,value)

        self._listen_task = None

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
        self._subscribed_event = gevent.event.Event()
        self._value_event = gevent.event.Event()
        
        self.__bus.subscribe(name, self)

        if not isinstance(value, NotInitialized):
            self.__bus.update_channel(name, value)

    @property
    def name(self):
        return self.__name

    @property
    def default_value(self):
        return self.__default_value

    @property 
    def value(self):
        if self.__name not in self.__bus._pubsub.channels: # not subscribed yet
            with gevent.Timeout(self.__timeout, RuntimeError("%s: timeout to subscribe to channel" % self.__name)):
                self._subscribed_event.wait()
        value = self.__bus.channel_value.get(self.__name)
        if value is None:
            with gevent.Timeout(self.__timeout, RuntimeError("%s: timeout to receive channel value" % self.__name)):
                self._value_event.wait()
                self._value_event.clear()
                value = self.__bus.channel_value.get(self.__name)
        return value.value

    @value.setter
    def value(self, new_value):
        self.__bus.update_channel(self.__name,new_value)

    @property
    def timeout(self):
        return self.__timeout

    @timeout.setter
    def timeout(self,value):
        self.__timeout = value

    def register_callback(self, callback):
        if callable(callback):
            cb_ref = saferef.safe_ref(callback)
            callback_refs = self.__bus.channel_cbk.setdefault(self.__name,set())
            callback_refs.add(cb_ref)

    def unregister_callback(self, callback):
        cb_ref = saferef.safe_ref(callback)
        try:
            callback_refs = self.__bus.channel_cbk.setdefault(self.__name,set())
            callback_refs.remove(cb_ref)
        except:
            return

    def __repr__(self):
        self.value
        return '%s->%s' % (self.__name, self.__bus.channel_value.get(self.__name))

def Channel(name, value=NotInitialized(), callback=None,
            default_value=None, redis=None):
    if redis is None:
        redis = client.get_cache()


    bus = Bus(redis)

    try:
        chan_ref = bus.channels[name]
        chan = chan_ref()
    except KeyError:
        chan = _Channel(bus, name, default_value, value)
    else:
        if not isinstance(value, NotInitialized):
            chan.value = value
   
    if callback is not None:
        chan.register_callback(callback)

    return chan

DEVICE_CACHE = weakref.WeakKeyDictionary()

def Cache(device,key,**keys):
    """
    Create a cache value for a device. Device object must have a *name* in his attributes.
    This class should be used to optimized the device access.
    i.e: Don't re-configure a device if it's already configured
    """
    try:
        device_name = device.name
    except AttributeError:
        raise RuntimeError("cache: can't create a cache value (%s), the device (%s) has no name" % (device,key))
    
    default_value = keys.get('default_value',None)
    cached_channels = DEVICE_CACHE.setdefault(device,dict())
    key_name = '%s:%s' % (device.name,key)
    cached_channels[key_name] = default_value
    return Channel(key_name,**keys)

def clear_cache(*devices) :
    """
    Clear cache for the associated devices
    devices -- one or more devices or if no device all devices
    """
    if not devices:
        devices = DEVICE_CACHE.keys()
    for d in devices:
        cached_channels = DEVICE_CACHE.get(d,dict())
        for channel_name,default_value in cached_channels.iteritems():
            chan = Channel(channel_name)
            chan.value = default_value
            
