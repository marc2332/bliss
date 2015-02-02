import weakref
import os,sys
import gevent
from gevent import socket,select,event,queue
from . import protocol
import redis

try:
    import posix_ipc
    class _PosixQueue(posix_ipc.MessageQueue):
        def __init__(self,rx_name,wx_name) :
            posix_ipc.MessageQueue.__init__(self,rx_name)
            self._wqueue = posix_ipc.MessageQueue(wx_name)

        def close(self):
            posix_ipc.MessageQueue.close(self)
            self._wqueue.close()

        def sendall(self,msg):
            max_message_size = self.max_message_size
            for i in range(0,len(msg),max_message_size):
                self._wqueue.send(msg[i:i+max_message_size])

except ImportError:
    posix_ipc = None

def check_connect(func) :
    def f(self,*args,**keys) :
        self.connect()
        return func(self,*args,**keys)
    return f

class ConnectionException(Exception):
  def __init__(self, *args, **kwargs):
    Exception.__init__(self, *args, **kwargs)

class Connection(object) :
    class WaitingLock(object):
        def __init__(self,cnt,priority,device_name) :
            self._cnt = weakref.ref(cnt)
            self._msg = '%d|%s' % (priority,'|'.join(device_name))
            self._queue = queue.Queue()

        def msg(self) :
            return self._msg

        def get(self) :
            return self._queue.get()

        def __enter__(self):
            cnt = self._cnt()
            pm = cnt._pending_lock.get(self._msg,[])
            if not pm:
                cnt._pending_lock[self._msg] = [self._queue]
            else:
                pm.append(self._queue)
            return self

        def __exit__(self,*args) :
            cnt = self._cnt()
            pm = cnt._pending_lock.pop(self._msg,[])
            if pm:
                try:
                    pm.remove(self._queue)
                except ValueError:
                    pass
                cnt._pending_lock[self._msg] = pm

    class WaitingQueue(object):
        def __init__(self,cnt) :
            self._cnt = weakref.ref(cnt)
            self._message_key = str(cnt._message_key)
            cnt._message_key += 1
            self._queue = queue.Queue()

        def message_key(self) :
            return self._message_key

        def get(self) :
            return self._queue.get()

        def queue(self) :
            return self._queue

        def __enter__(self) :
            cnt = self._cnt()
            cnt._message_queue[self._message_key] = self._queue
            return self

        def __exit__(self,*args) :
            cnt = self._cnt()
            cnt._message_queue.pop(self._message_key,None)

    def __init__(self,host=None,port=None) :
        self._socket = None
        if host is None:
            host = os.environ.get("BEACON_HOST",None)
        self._host = host
        self._port = port
        self._pending_lock = {}
        self._g_event = event.Event()
        self._message_key = 0
        self._message_queue = {}
        self._clean()
        self._fd = None
        self._cnx = None
        self._raw_read_task = None

    def close(self) :
        if self._fd:
            self._fd.close()
            self._fd = None
            self._raw_read_task.join()
            self._raw_read_task = None
            self._cnx = None

    def connect(self) :
        host = self._host
        port = self._port
        if self._fd is None:
            #try to find the server on the same sub-net
            if host is None or port is  None:
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                udp.bind(("",protocol.DEFAULT_UDP_CLIENT_PORT))
                udp.sendto('Hello',('255.255.255.255',protocol.DEFAULT_UDP_SERVER_PORT))
                timeout = 10.
                while 1:
                    rlist,_,_ = select.select([udp],[],[],timeout)
                    if not rlist:
                        if port is None:
                            raise ConnectionException("Could not find the conductor")
                        else:
                            break
                    else:
                        msg,address = udp.recvfrom(8192)
                        host,port = msg.split('|')
                        port = int(port)
                        if self._host is not None and host != self._host:
                            host,port = None,None
                            timeout = 1.
                        else:
                            break
                            
            self._fd = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            self._fd.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            self._fd.connect((host,port))
            self._raw_read_task = gevent.spawn(self._raw_read)
            self._cnx = self._fd
            if posix_ipc:
                self._g_event.clear()
                self._fd.sendall(protocol.message(protocol.POSIX_MQ_QUERY,socket.gethostname()))
                self._g_event.wait(1.)
            
    @check_connect
    def lock(self,devices_name,**params):
        priority = params.get('priority',50)
        timeout = params.get('timeout',10)
        if len(devices_name) == 0: return # don't need to ask ;)
        with self.WaitingLock(self,priority,devices_name) as wait_lock:
            with gevent.Timeout(timeout,
                                RuntimeError("lock timeout (%s)" % str(devices_name))):
                while 1:
                    self._cnx.sendall(protocol.message(protocol.LOCK,wait_lock.msg()))
                    status = wait_lock.get()
                    if status == protocol.LOCK_OK_REPLY: break

    @check_connect
    def unlock(self,devices_name,**params) :
        timeout = params.get('timeout',1)
        priority = params.get('priority',50)
        if len(devices_name) == 0: return
        msg = "%d|%s" % (priority,'|'.join(devices_name))
        with gevent.Timeout(timeout,RuntimeError("unlock timeout (%s)" % str(devices_name))):
            self._cnx.sendall(protocol.message(protocol.UNLOCK,msg))

    @check_connect
    def get_redis_connection_addtess(self) :
        if self._redis_host is None:
            with gevent.Timeout(1,RuntimeError("Can't get redis connection information")):
                while self._redis_host is None:
                    self._g_event.clear()
                    self._fd.sendall(protocol.message(protocol.REDIS_QUERY))
                    self._g_event.wait()

        return self._redis_host,self._redis_port

    @check_connect
    def get_redis_connection(self,db=0):
        cnx = self._redis_connection.get(db)
        if cnx is None :
            host,port = self.get_redis_connection_addtess()
            cnx = redis.Redis(host=host,port=port,db=db)
            self._redis_connection[db] = cnx
        return cnx

    @check_connect
    def get_config_file(self,file_path,timeout = 10.) :
        with gevent.Timeout(timeout,RuntimeError("Can't get configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = '%s|%s' % (wq.message_key(),file_path)
                self._fd.sendall(protocol.message(protocol.CONFIG_GET_FILE,msg))
                value = wq.get()
                if isinstance(value,RuntimeError):
                    raise value
                else:
                    return value
    @check_connect
    def get_config_db(self,base_path='',timeout = 30.):
        return_files = []
        with gevent.Timeout(timeout,RuntimeError("Can't get configuration file")):
            with self.WaitingQueue(self) as wq:
                msg = '%s|%s' % (wq.message_key(),base_path)
                self._fd.sendall(protocol.message(protocol.CONFIG_GET_DB_BASE_PATH,msg))
                for rx_msg in wq.queue():
                    file_path,file_value = self._get_msg_key(rx_msg)
                    if file_path is None : continue
                    return_files.append((file_path,file_value))
        return return_files

    def _lock_mgt(self,fd,messageType,message):
        if messageType == protocol.LOCK_OK_REPLY:
            events = self._pending_lock.get(message,[])
            if not events:
                fd.sendall(protocol.message(protocol.UNLOCK,
                                            message))
            else:
                e = events.pop(0)
                e.put(messageType)
            return True
        elif messageType == protocol.LOCK_RETRY:
            for m,l in self._pending_lock.iteritems():
                for e in l: e.put(messageType)
            return True
        return False

    def _get_msg_key(self,message) :
        pos = message.find('|')
        if pos < 0: return None,None
        return message[:pos],message[pos + 1:]

    def _raw_read(self) :
        try:
            data = ''
            mq_pipe = None
            while(1):
                raw_data = self._fd.recv(16 * 1024)
                if not raw_data: break
                data = '%s%s' % (data,raw_data)
                while data:
                    try:
                        messageType,message,data = protocol.unpack_message(data)
                    except ValueError:
                        break
                    try:
                        #print 'rx',messageType
                        if self._lock_mgt(self._fd,messageType,message):
                            continue
                        elif(messageType == protocol.CONFIG_GET_FILE_OK or
                             messageType == protocol.CONFIG_DB_FILE_RX):
                            message_key,value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None: queue.put(value)
                        elif messageType == protocol.CONFIG_GET_FILE_FAILED:
                            message_key,value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None: queue.put(RuntimeError(value))
                        elif messageType == protocol.CONFIG_DB_END:
                            message_key,value = self._get_msg_key(message)
                            queue = self._message_queue.get(message_key)
                            if queue is not None: queue.put(StopIteration)
                        elif messageType == protocol.REDIS_QUERY_ANSWER:
                            self._redis_host,self._redis_port = message.split(':')
                            self._g_event.set()
                        elif messageType == protocol.POSIX_MQ_OK:
                            self._cnx = _PosixQueue(*message.split('|'))
                            self._cnx.sendall(protocol.message(protocol.POSIX_MQ_OPENED))
                            mq_pipe,wp = os.pipe()
                            gevent.spawn(self._mq_read,self._cnx,wp)
                            self._g_event.set()
                        elif messageType == protocol.POSIX_MQ_FAILED:
                            self._g_event.set()
                    except:
                        sys.excepthook(*sys.exc_info())
        except socket.error:
            pass
        except:
            import traceback
            traceback.print_exc()
        finally:
            if self._fd:
                self._fd.close()
                self._fd = None
            if mq_pipe is not None:
                os.close(mq_pipe)
            self._clean()

    def _mq_read(self,queue,pipe):
        try:
            data = ''
            stopFlag = False
            while not stopFlag:
                r,_,_ = select.select([queue.mqd,pipe],[],[])
                for f in r:
                    if f == pipe:
                        stopFlag = True
                        break
                    else:
                        data = '%s%s' % (data,queue.receive()[0])
                        while data:
                            try:
                                messageType,message,data = protocol.unpack_message(data)
                                self._lock_mgt(queue,messageType,message)
                            except ValueError:
                                pass
        except:
            import traceback
            traceback.print_exc()
        finally:
            queue.close()
            os.close(pipe)

    def _clean(self) :
        self._redis_host = None
        self._redis_port = None
        try:
            for db,redis_cnx in self._redis_connection.iteritems():
                redis_cnx.disconnect()
        except:
            pass
        self._redis_connection = {}

_default_connection = Connection()

        
class Client(object):
    @staticmethod
    def lock(*devices,**params):
        devices_name = [d.name for d in devices]
        _default_connection.lock(devices_name,**params)
    @staticmethod
    def unlock(*devices,**params):
        devices_name = [d.name for d in devices]
        _default_connection.unlock(devices_name,**params)
    @staticmethod
    def get_cache_address():
        return _default_connection.get_redis_connection_addtess()
    @staticmethod
    def get_cache(db=0):
        return _default_connection.get_redis_connection(db=db)
    @staticmethod
    def get_config_file(file_path) :
        return _default_connection.get_config_file(file_path)
    @staticmethod
    def get_config_db_files(base_path='',timeout=30.):
        path2files = _default_connection.get_config_db(base_path=base_path,timeout=timeout)
        return path2files
