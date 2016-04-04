from .conductor import client
from collections import namedtuple
from functools import partial
import cPickle
import gevent
import gevent.event
import time
from bliss.common.utils import grouped
# use safe reference module from dispatcher
# (either louie -the new project- or pydispatch)
try:
    from louie import saferef
except ImportError:
    from pydispatch import saferef
    saferef.safe_ref = saferef.safeRef
import weakref
import sys
import os

CHANNELS = dict()
CHANNELS_VALUE = dict()
CHANNELS_CBK = dict()
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
    class WaitEvent(object):
        def __init__(self,bus,name) :
            self._bus = bus
            self._name = name
            self._event = gevent.event.Event()
            
        def __enter__(self):
            wait_set = self._bus._wait_event.setdefault(self._name,set())
            wait_set.add(self)
            self._event.clear()
            return self

        def __exit__(self,*args):
            wait_set = self._bus._wait_event.setdefault(self._name,set())
            wait_set.remove(self)
            if not wait_set:
                self._bus._wait_event.pop(self._name)

        def set(self):
            self._event.set()

        def wait(self):
            self._event.clear()
            self._event.wait()

    def __init__(self, redis):
        self._redis = redis
        self._pubsub = redis.pubsub()
        self._pending_subscribe = list()
        self._pending_unsubscribe = list()
        self._pending_channel_value = dict()
        self._pending_init = list()
        self._send_event = gevent.event.Event()
        self._in_recv = False
        self._wait_event = dict()

        self._listen_task = None
        self._send_task = gevent.spawn(self._send)

    def subscribe(self,names):
        if isinstance(names,str):
            self._pending_subscribe.append(names)
        else:
            self._pending_subscribe.extend(names)
        self._send_event.set()

    def get_init_value(self,name,default_value):
        self._pending_init.append((name,default_value))
        self._send_event.set()

    def unsubscribe(self,names):
        if isinstance(names,str):
            self._pending_unsubscribe.append(names)
        else:
            self._pending_unsubscribe.extend(names)
        self._send_event.set()

    def wait_event_on(self,name):
        return _Bus.WaitEvent(self,name)

    def update_channel(self,name,value):
        if isinstance(value,_ChannelValue):
            prev_channel_value = CHANNELS_VALUE.get(name)
            if(prev_channel_value is None or 
               prev_channel_value.timestamp < value.timestamp):
                channel_value = value
            else:
                return          # already up-to-date
            CHANNELS_VALUE[name] = channel_value
            self._fire_notification_callbacks(name)
        else:
            channel_value = _ChannelValue(None,value)


        if not self._in_recv:
            self._pending_channel_value[name] = channel_value
            self._send_event.set()
    
    def _fire_notification_callbacks(self,name):
        deleted_cb = set()
        for cb_ref in CHANNELS_CBK.get(name,set()):
            cb = cb_ref()
            if cb is not None:
                try:
                    cb(CHANNELS_VALUE.get(name).value)
                except:
                    # display exception, but do not stop
                    # executing callbacks
                    sys.excepthook(*sys.exc_info())
            else:
                deleted_cb.add(cb_ref)
        CHANNELS_CBK.get('name',set()).difference_update(deleted_cb)

    def _send(self):
        while(1):
            self._send_event.wait()
            self._send_event.clear()
 
            #local transfer
            pending_subscribe = self._pending_subscribe
            pending_unsubscribe = self._pending_unsubscribe
            pending_channel_value = self._pending_channel_value
            pending_init = self._pending_init
            pubsub = self._pubsub

            self._pending_subscribe = list()
            self._pending_unsubscribe = list()
            self._pending_channel_value = dict()
            self._pending_init = list()

            no_listener_4_values = set()
            if pending_subscribe:
                result = self._redis.execute_command('pubsub','numsub',*pending_subscribe)
                no_listener_4_values = set((name for name,nb_listener in grouped(result,2) if nb_listener is '0'))
                pubsub.subscribe(pending_subscribe)
                if self._listen_task is None:
                    self._listen_task = gevent.spawn(self._listen)

            if pending_unsubscribe: pubsub.unsubscribe(pending_unsubscribe)

            if pending_channel_value:
                pipeline = self._redis.pipeline()
                for name,channel_value in pending_channel_value.iteritems():
                    if channel_value.timestamp is None:
                        channel_value = _ChannelValue(time.time(),channel_value.value)
                    pipeline.publish(name,cPickle.dumps(channel_value,protocol=-1))
                pipeline.execute()

            if pending_init:
                pipeline = self._redis.pipeline()
                for name,default_value in pending_init:
                    if name not in no_listener_4_values:
                        pipeline.publish(name,cPickle.dumps(ValueQuery(),protocol=-1))
                    else: # we are alone
                        CHANNELS_VALUE[name] = _ChannelValue(None,default_value)
                        for waiting_event in self._wait_event.get(name,set()):
                            waiting_event.set()
                pipeline.execute()

    def _listen(self):
        for event in self._pubsub.listen():
            event_type = event.get('type')
            if event_type == 'message':
                value = cPickle.loads(event.get('data'))
                channel_name = event.get('channel')
                if isinstance(value,ValueQuery):
                    channel_value = CHANNELS_VALUE.get(channel_name)
                    if channel_value is not None:
                        self._pending_channel_value[channel_name] = channel_value
                        self._send_event.set()
                else:
                    self._in_recv = True
                    self.update_channel(channel_name,value)
                    self._in_recv = False
                    for waiting_event in self._wait_event.get(channel_name,set()):
                        waiting_event.set()

        self._listen_task = None

def Bus(redis):
    try:
        return BUS[redis]
    except KeyError:
        bus = _Bus(redis)
        BUS[redis] = bus
        return bus

class _Channel(object):
    def __init__(self, redis, name, default_value,value):
        self._bus = Bus(redis)

        self._bus.subscribe(name)
        def on_die(killed_ref):
            # don't use 'self' otherwise it creates a cycle
            bus = Bus(redis)
            bus.unsubscribe(name)
            CHANNELS_VALUE.pop(name, None)
            CHANNELS_CBK.pop(name, None)
            CHANNELS.pop(name, None) 
        CHANNELS[name] = weakref.ref(self, on_die)
        self.__name = name
        self.__timeout = 3.
        if not isinstance(value ,NotInitialized):
            self._bus.update_channel(name,value)
        else:
            self._bus.get_init_value(name,default_value)

    @property
    def name(self):
        return self.__name

    @property 
    def value(self):
        value = CHANNELS_VALUE.get(self.__name)
        if value is None:       # probably not initialized
            with gevent.Timeout(self.__timeout, RuntimeError("%s: timeout to receive channel value" % self.__name)):
                while value is None:
                    with self._bus.wait_event_on(self.__name) as we:
                        we.wait()
                        value = CHANNELS_VALUE.get(self.__name)
                    
        return value.value

    @value.setter
    def value(self, new_value):
        self._bus.update_channel(self.__name,new_value)

    @property
    def timeout(self):
        return self.__timeout

    @timeout.setter
    def timeout(self,value):
        self.__timeout = value

    def register_callback(self, callback):
        if callable(callback):
            cb_ref = saferef.safe_ref(callback)
            callback_refs = CHANNELS_CBK.setdefault(self.__name,set())
            callback_refs.add(cb_ref)

    def unregister_callback(self, callback):
        cb_ref = saferef.safe_ref(callback)
        try:
            callback_refs = CHANNELS_CBK.setdefault(self.__name,set())
            callback_refs.remove(cb_ref)
        except:
            return

    def __repr__(self):
        self.value
        return '%s->%s' % (self.__name,CHANNELS_VALUE.get(self.__name))

def Channel(name, value=NotInitialized(), callback=None,
            default_value=None, redis=None):
    if redis is None:
            redis = client.get_cache()
    try:
        chan_ref = CHANNELS[name]
        chan = chan_ref()
    except KeyError:
        chan = _Channel(redis, name,default_value, value)

    if callback is not None:
        chan.register_callback(callback)
    return chan

