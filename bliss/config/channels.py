from .conductor import client
import nanomsg
import cPickle
import socket
import atexit
import gevent
import gevent.event
import gevent.monkey
# always use real time, select and threading module
from gevent import _threading as threading
import functools
import select
import time
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
BUS = weakref.WeakValueDictionary()
BUS_BY_FD = weakref.WeakValueDictionary()
SURVEYORS = dict()
RECEIVER_THREAD = None
THREAD_ENDED = threading.Event()

CHANNELS_BUS = 'channels_bus'
CHANNELS_RESPONDENT = 'channels_respondent'

# getting the first free port available in range 30000-40000
def get_free_port(redis,channel_key):
    for port_number in xrange(30000,40000) :
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind(('', port_number))
            except:
                continue
            free_port_number = s.getsockname()[1]
            url = "tcp://%s:%d" % (socket.getfqdn(), free_port_number)
            if redis.sadd(channel_key,url) == 1: # the port is not used
                break
        finally:
            s.close()
    else:
        raise RuntimeError("No free TCP port in range (30000,40000)")
    return free_port_number


class NotInitialized(object):
    def __repr__(self):
        return "NotInitialized"
    def __eq__(self, other):
        if isinstance(other, NotInitialized):
            return True
        return False


def get_file_descriptors():
    # .keys() is atomic (takes GIL)
    fds = [WAKE_UP_SOCKET_R.recv_fd] + BUS_BY_FD.keys() + SURVEYORS.keys()
    return fds


def update_channel(bus_id, channel_name, value):
    try:
        channel = CHANNELS[bus_id][channel_name]
    except KeyError:
        pass
    else:
        # simple assignment is atomic 
       channel._value = value
       channel._update_watcher.send()


def receive_channels_values():
    fds = get_file_descriptors()
    while True:
        readable_fds, _, _ = select.select(fds, [], [])
        for fd in readable_fds:
            if fd == WAKE_UP_SOCKET_R.recv_fd:
                if WAKE_UP_SOCKET_R.recv() == '$':
                    THREAD_ENDED.set()
                    return
                fds = get_file_descriptors() 
                break
            else:
                bus_id, channel_name, s = SURVEYORS.get(fd, (None,None,None))
                if s:
                    close_survey = False

                    if s.send_fd == fd and not s.survey_sent:
                        if s.survey_sent is None:
                            time.sleep(0.01) # give some time for connections to be established
                            s.tries = 1
                        #print os.getpid(), "sending survey", channel_name, time.time()
                        s.send(channel_name)
                        s.survey_sent = True
                    elif s.recv_fd == fd and s.survey_sent:
                        #print os.getpid(), "surveyor readable", time.time()
                        try:
                            value = cPickle.loads(s.recv())
                        except nanomsg.NanoMsgAPIError:
                            # nobody replied to survey within the 1 second timeout,
                            # too bad :(
                            #print os.getpid(), 'no reply to survey', time.time()
                            # send again
                            s.survey_sent = False
                            s.tries += 1
                            if s.tries > 3:
                                close_survey = True
                        else:
                            close_survey = True
                            update_channel(bus_id, channel_name, value) 

                    if close_survey:
                        del SURVEYORS[s.recv_fd]
                        del SURVEYORS[s.send_fd]
                        #print os.getpid(), 'closing socket'
                        s.close()
                        fds = get_file_descriptors()
                else:
                    try:
		        bus = BUS_BY_FD[fd]
	            except KeyError:
                        continue
	            else:
		        if fd == bus._respondent_socket.recv_fd: 
		            channel_name = bus._respondent_socket.recv()
		            try:
			        channel = CHANNELS[bus.id][channel_name]
		            except KeyError:
			        continue
		            else:
			        #print os.getpid(), 'replying to survey'
			        bus._respondent_socket.send(cPickle.dumps(channel.value, protocol=-1))
                                del channel
		        else:
		            channel_name, value = cPickle.loads(bus.recv()) 
                            update_channel(bus.id, channel_name, value)


def _clean_redis(redis, channels_bus, channels_respondent):
    redis.srem(CHANNELS_BUS, channels_bus)
    redis.srem(CHANNELS_RESPONDENT, channels_respondent)

def stop_receiver_thread():
    if RECEIVER_THREAD is not None:
        WAKE_UP_SOCKET_W.send("$")
        # join thread
        THREAD_ENDED.wait()
         

class _Bus(object):
    def __init__(self, redis, bus_id, channels_bus_list):   
        self._id = bus_id

        # create sockets
        self._bus_socket = nanomsg.Socket(nanomsg.BUS)
        self._respondent_socket = nanomsg.Socket(nanomsg.RESPONDENT)

        bus_socket_port_number = get_free_port(redis,CHANNELS_BUS)
        self._bus_socket.bind("tcp://*:%d" % bus_socket_port_number)
        BUS_BY_FD[self.recv_fd] = self
        # connect to other bus sockets     
        for remote_bus in channels_bus_list:
            self._bus_socket.connect(remote_bus)
        self.__bus_addr = "tcp://%s:%d" % (socket.getfqdn(), bus_socket_port_number)

        # respondent socket is used to reply to survey requests 
        respondent_socket_port_number = get_free_port(redis,CHANNELS_RESPONDENT)
        self._respondent_socket.bind("tcp://*:%d" % respondent_socket_port_number)
        BUS_BY_FD[self._respondent_socket.recv_fd] = self
        self.__bus_respondent_addr = "tcp://%s:%d" % (socket.getfqdn(), respondent_socket_port_number)
        
        # remove addresses in redis at exit
        atexit.register(_clean_redis, redis, self.addr, self.respondent_addr)

        # receiver thread takes care of dispatching received values to right channels
        global RECEIVER_THREAD
        if RECEIVER_THREAD is None:
            global WAKE_UP_SOCKET_W
            global WAKE_UP_SOCKET_R
            WAKE_UP_SOCKET_W = nanomsg.Socket(nanomsg.PAIR)
            WAKE_UP_SOCKET_W.bind("inproc://beacon/channels/wake_up_loop")
            WAKE_UP_SOCKET_R = nanomsg.Socket(nanomsg.PAIR)
            WAKE_UP_SOCKET_R.connect("inproc://beacon/channels/wake_up_loop")
            RECEIVER_THREAD = threading.start_new_thread(receive_channels_values, ()) 
            atexit.register(stop_receiver_thread)
        else:
            WAKE_UP_SOCKET_W.send('!')

    @property
    def addr(self):
        return self.__bus_addr

    @property
    def respondent_addr(self):
        return self.__bus_respondent_addr

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    @property
    def recv_fd(self):
        return self._bus_socket.recv_fd

    def recv(self, *args, **kwargs):
        return self._bus_socket.recv(*args, **kwargs)

    def set_value(self, channel_name, new_value):
        self._bus_socket.send(cPickle.dumps((channel_name, new_value), protocol=-1))                


def call_notification_callbacks(bus_id, channel_name):
    try:
        channel = CHANNELS[bus_id][channel_name]
    except KeyError:
        return
    else:
        channel._fire_notification_callbacks()


class _Channel(object):
    def __init__(self, redis, bus_id, name, value, callback=None):
        self._redis = redis
        self._name = name
        self._value = NotInitialized()
        self._callback = callback
        self._update_watcher = gevent.get_hub().loop.async()
        self._update_watcher.start(functools.partial(call_notification_callbacks, bus_id, name))
        self._callback_refs = set() 
        self._initialized_event = gevent.event.Event()

        self.register_callback(callback)

        self._bus = BUS.get(bus_id)
        if self._bus is None:
            channels_bus_list = redis.smembers(CHANNELS_BUS)
            self._bus = _Bus(redis, bus_id, channels_bus_list) 
            BUS[bus_id] = self._bus
            
    @property
    def name(self):
        return self._name

    @property 
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        if new_value == self._value:
            return
        self._initialized_event.set()
        self._value = new_value
        self._bus.set_value(self.name, new_value) 

    def init(self):
        self._initialized_event.clear()

        s = nanomsg.Socket(nanomsg.SURVEYOR)
        s.survey_sent = None
        s.set_int_option(nanomsg.SURVEYOR, nanomsg.SURVEYOR_DEADLINE, 1000)

        # ask for channel value to all respondents
        respondent_list = self._redis.smembers("channels_respondent")
        for respondent in respondent_list:
            if respondent != self._bus.respondent_addr:
                #print 'connecting to',respondent
                s.connect(respondent)
 
        SURVEYORS[s.send_fd] = (self._bus.id, self.name, s)
        SURVEYORS[s.recv_fd] = (self._bus.id, self.name, s)

        WAKE_UP_SOCKET_W.send('!')

    def register_callback(self, callback):
        if callable(callback):
            cb_ref = saferef.safe_ref(callback)
            self._callback_refs.add(cb_ref)

    def unregister_callback(self, callback):
        cb_ref = saferef.safe_ref(callback)
        try:
            self._callback_refs.remove(cb_ref)
        except:
            return

    def _fire_notification_callbacks(self):
        self._initialized_event.set()
        if self.value == NotInitialized():
            return
        for cb_ref in self._callback_refs:
            cb = cb_ref()
            if cb is not None:
                try:
                    cb(self.value)
                except:
                    # display exception, but do not stop
                    # executing callbacks
                    sys.excepthook(*sys.exc_info())

    def wait_initialized(self, timeout=None):
        self._initialized_event.wait(timeout)
      

def Channel(name, value=NotInitialized(), callback=None, wait=True, timeout=1, redis=None):
    if redis is None:
            redis = client.get_cache()
    redis_connection_args = redis.connection_pool.connection_kwargs
    bus_id = (redis_connection_args['host'], redis_connection_args['port'], redis_connection_args['db'])

    try:
        chan = CHANNELS[bus_id][name]
    except KeyError:
        chan = _Channel(redis, bus_id, name, value, callback)
   
    if value == NotInitialized():
        # ask peers for channel value
        chan.init()
    else:
        # set value for channel, and notify peers
        chan.value = value

    CHANNELS.setdefault(bus_id, weakref.WeakValueDictionary())[name] = chan
    
    if wait:
        chan.wait_initialized(timeout)

    return chan

