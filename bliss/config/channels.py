from .conductor import client
import nanomsg
import cPickle
import socket
import atexit
from gevent import select
# always use real threading module
from gevent import _threading as threading
import gevent
import weakref
# use safe reference module from dispatcher
# (either louie -the new project- or pydispatch)
try:
    from louie import saferef
except ImportError:
    from pydispatch import saferef
    saferef.safe_ref = saferef.safeRef

CHANNELS = dict()
BUS = weakref.WeakValueDictionary()
BUS_BY_FD = dict()
RECEIVER_THREAD = None


# clumsy way of getting free port number
# I hate this but I don't know how to do
# better...
# nanomsg doesn't have the possibility to
# bind to any free port, we *have* to provide
# a free one
def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    free_port_number = s.getsockname()[1]
    s.close()

    return free_port_number


class NotInitialized(object):
    def __repr__(self):
        return "NotInitialized"


def receive_channels_values():
    while True:
        fds = BUS_BY_FD.keys()
        readable_fds, _, _ = select.select(fds, [], [], 1)
        for fd in readable_fds:
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
                        bus._respondent_socket.send("")
                    else:
                        bus._respondent_socket.send(cPickle.dumps(channel.value, protocol=-1))
                else:
                    channel_name, value = cPickle.loads(bus.recv()) 
                    try:
                        channel = CHANNELS[bus.id][channel_name]
                    except KeyError:
                        continue
                    else:
                        # simple assignment is atomic 
                        channel._value = value
                        channel._update_watcher.send()


def _clean_redis(redis, channels_bus, channels_respondent):
    redis.srem("channels_bus", channels_bus)
    redis.srem("channels_respondent", channels_respondent)


class _Bus(object):
    def __init__(self, bus_id, redis):   
        self._id = bus_id
        # create sockets
        self._bus_socket = nanomsg.Socket(nanomsg.BUS)
        self._respondent_socket = nanomsg.Socket(nanomsg.RESPONDENT)

        bus_socket_port_number = get_free_port()
        self._bus_socket.bind("tcp://*:%d" % bus_socket_port_number)
        BUS_BY_FD[self.recv_fd] = self
        # connect to other bus sockets     
        channels_bus_list = redis.smembers("channels_bus")
        for remote_bus in channels_bus_list:
            self._bus_socket.connect(remote_bus)
        # add socket to the set of channels bus sockets
        bus_addr = "tcp://%s:%d" % (socket.getfqdn(), bus_socket_port_number)
        redis.sadd("channels_bus", bus_addr)
        
        # respondent socket is used to reply to survey requests 
        respondent_socket_port_number = get_free_port()
        self._respondent_socket.bind("tcp://*:%d" % respondent_socket_port_number)
        BUS_BY_FD[self._respondent_socket.recv_fd] = self
        # add surveyor socket in list
        respondent_addr = "tcp://%s:%d" % (socket.getfqdn(), respondent_socket_port_number)
        redis.sadd("channels_respondent", respondent_addr)

        atexit.register(_clean_redis, redis, bus_addr, respondent_addr)
            
        # receiver thread takes care of dispatching received values to right channels
        global RECEIVER_THREAD
        if RECEIVER_THREAD is None:
            RECEIVER_THREAD = threading.start_new_thread(receive_channels_values, ())

    @property
    def name(self):
        return self._name

    @property
    def id(self):
        return self._id

    @property
    def recv_fd(self):
        return self._bus_socket.recv_fd

    def recv(self):
        return self._bus_socket.recv()

    def set_value(self, channel_name, new_value):
        self._bus_socket.send(cPickle.dumps((channel_name, new_value), protocol=-1))                

    def get_channel_value(self, channel_name, redis):
        # ask for channel value to all respondents
        s = nanomsg.Socket(nanomsg.SURVEYOR)

        respondent_list = redis.smembers("channels_respondent")
        for respondent in respondent_list:
            s.connect(respondent) 

        gevent.sleep(0.1) #why in the hell is this sleep necessary???
        
        s.send(channel_name) 
        
        while True:
            try:
                data = s.recv()
            except:
                s.close()
                return NotInitialized()
            else:
                if data:
                    s.close()
                    return cPickle.loads(data)


class _Channel(object):
    def __init__(self, bus_id, name, redis):
        self._name = name
        self._update_watcher = gevent.get_hub().loop.async()
        self._update_watcher.start(self._fire_notification_callbacks)
        self._callback_refs = set()

        self._bus = BUS.get(bus_id)
        if self._bus is None:
            self._bus = _Bus(bus_id, redis) 
            BUS[bus_id] = self._bus

        self._value = self._bus.get_channel_value(self.name, redis) 

        CHANNELS.setdefault(bus_id, weakref.WeakValueDictionary())[self.name] = self

    @property
    def name(self):
        return self._name

    @property 
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value
        self._bus.set_value(self.name, new_value) 

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
        for cb_ref in self._callback_refs:
            cb = cb_ref()
            if cb is not None:
                try:
                    cb(self.value)
                except:
                    # display exception, but do not stop
                    # executing callbacks
                    sys.excepthook(*sys.exc_info())


def Channel(name, redis=None):
    if redis is None:
            redis = client.get_cache()
    redis_connection = redis.connection_pool.get_connection("")
    bus_id = (redis_connection.host, redis_connection.port, redis_connection.db)

    try:
        return CHANNELS[bus_id][name]
    except KeyError:
        return _Channel(bus_id, name, redis)


