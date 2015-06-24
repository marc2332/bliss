import os
import sys
import argparse
import weakref
import subprocess
import gevent
import signal
from gevent import select, socket

def start_database_ds(tango_port = 20000,personal_name='2',debug_level = 0):
    from PyTango.databaseds import database
    argv = debug_level and ['-l',str(debug_level)] or []
    argv.extend(['--db_access','beacon','--port',str(tango_port),'2'])
    database.main(argv=argv)

from . import protocol
from .. import redis as redis_conf
try:
    import posix_ipc
except ImportError:
    posix_ipc = None
else:
    class _PosixQueue(posix_ipc.MessageQueue):
        def __init__(self):
            posix_ipc.MessageQueue.__init__(self,None,mode=0666,
                                            flags=posix_ipc.O_CREX)
            self._wqueue = posix_ipc.MessageQueue(None,mode=0666,
                                                  flags=posix_ipc.O_CREX)
        def unlink(self) :
            posix_ipc.MessageQueue.unlink(self)
            self._wqueue.unlink()

        def close(self) :
            posix_ipc.MessageQueue.close(self)
            self._wqueue.close()

        def names(self):
            return self._wqueue.name,self.name

        def sendall(self,msg) :
            max_message_size = self.max_message_size
            for i in xrange(0,len(msg),max_message_size):
                self._wqueue.send(msg[i:i+max_message_size])

_options = None
_lock_object = {}
_client_to_object = weakref.WeakKeyDictionary()
_waiting_lock = weakref.WeakKeyDictionary()

def _releaseAllLock(client_id):
#    print '_releaseAllLock',client_id
    objset = _client_to_object.pop(client_id,set())
    for obj in objset:
#        print 'release',obj
        _lock_object.pop(obj)

def _lock(client_id,prio,lock_obj,raw_message) :
#    print '_lock_object',_lock_object
#    print
    all_free = True
    for obj in lock_obj:
        socket_id,compteur,lock_prio = _lock_object.get(obj,(None,None,None))
        if socket_id and socket_id != client_id:
            if prio > lock_prio : continue
            all_free = False
            break

    if all_free:
        stolen_lock = {}
        for obj in lock_obj:
            socket_id,compteur,lock_prio = _lock_object.get(obj,(client_id,0,prio))
            if socket_id != client_id: # still lock
                pre_obj = stolen_lock.get(socket_id,None)
                if pre_obj is None:
                    stolen_lock[socket_id] = [obj]
                else:
                    pre_obj.append(obj)
                _lock_object[obj] = (client_id,1,prio)
                objset = _client_to_object.get(socket_id,set())
                objset.remove(obj)
            else:
                compteur += 1
                new_prio = lock_prio > prio and lock_prio or prio
                _lock_object[obj] = (client_id,compteur,new_prio)

        for client,objects in stolen_lock.iteritems():
            client.sendall(protocol.message(protocol.LOCK_STOLLEN,'|'.join(objects)))

        obj_already_locked = _client_to_object.get(client_id,set())
        _client_to_object[client_id] = set(lock_obj).union(obj_already_locked)

        client_id.sendall(protocol.message(protocol.LOCK_OK_REPLY,raw_message))
    else:
        _waiting_lock[client_id] = lock_obj

#    print '_lock_object',_lock_object

def _unlock(client_id,priority,unlock_obj) :
    unlock_object = []
    client_locked_obj = _client_to_object.get(client_id,None)
    if client_locked_obj is None:
        return

    for obj in unlock_obj:
        socket_id,compteur,prio = _lock_object.get(obj,(None,None,None))
#        print socket_id,compteur,prio,obj
        if socket_id and socket_id == client_id:
            compteur -= 1
            if compteur <= 0:
                _lock_object.pop(obj)
                try:
                    client_locked_obj.remove(obj)
                    _lock_object.pop(obj)
                except KeyError:
                    pass
                unlock_object.append(obj)
            else:
                _lock_object[obj] = (client_id,compteur,prio)

    unlock_object = set(unlock_object)
    tmp_dict = dict(_waiting_lock)
    for client_sock,tlo in tmp_dict.iteritems():
        try_lock_object = set(tlo)
        if try_lock_object.intersection(unlock_object) :
            objs = _waiting_lock.pop(client_sock)
            client_sock.sendall(protocol.message(protocol.LOCK_RETRY))

#    print '_lock_object',_lock_object

def _clean(client):
    _releaseAllLock(client)

def _send_redis_info(client_id):
    client_id.sendall(protocol.message(protocol.REDIS_QUERY_ANSWER,
                                    '%s:%d' % (socket.gethostname(),_options.redis_port)))

def _send_config_file(client_id,message):
    try:
        message_key,file_path = message.split('|')
    except ValueError:          # message is bad, skip it
        return
    file_path = file_path.replace('../','') # prevent going up
    full_path = os.path.join(_options.db_path,file_path)
    try:
        with open(full_path) as f:
            buffer = f.read()
            client_id.sendall(protocol.message(protocol.CONFIG_GET_FILE_OK,'%s|%s' % (message_key,buffer)))
    except IOError:
        client_id.sendall(protocol.message(protocol.CONFIG_GET_FILE_FAILED,"%s|File doesn't exist" % (message_key)))

def _send_config_db_files(client_id,message):
    try:
        message_key,sub_path = message.split('|')
    except ValueError:          # message is bad, skip it
        return
    sub_path = sub_path.replace('../','') # prevent going up
    look_path = sub_path and os.path.join(_options.db_path,sub_path) or _options.db_path
    try:
        for root,dirs,files in os.walk(look_path):
            for filename in files:
                basename,ext = os.path.splitext(filename)
                if ext == '.yml':
                    full_path = os.path.join(root,filename)
                    rel_path = full_path[len(_options.db_path) + 1:]
                    with file(full_path) as f:
                        raw_buffer = f.read()
                        msg = protocol.message(protocol.CONFIG_DB_FILE_RX,'%s|%s|%s' % (message_key,rel_path,raw_buffer))
                        client_id.sendall(msg)
    except:
        import traceback
        traceback.print_exc()
    finally:
        client_id.sendall(protocol.message(protocol.CONFIG_DB_END,"%s|" % (message_key)))

def _write_config_db_file(client_id,message):
    first_pos = message.find('|')
    second_pos = message.find('|',first_pos + 1)

    if first_pos < 0 or second_pos < 0: # message malformed
        msg = protocol.message(protocol.CONFIG_SET_DB_FILE_FAILED,
                               '%s|%s' % (message_key,'Malformed message'))
        client_id.sendall(msg)
        return

    message_key = message[:first_pos]
    file_path = message[first_pos + 1:second_pos]
    content = message[second_pos + 1:]
    file_path = file_path.replace('../','') # prevent going up
    full_path = os.path.join(_options.db_path,file_path)
    try:
        with file(full_path,'w') as f:
            f.write(content)
            msg = protocol.message(protocol.CONFIG_SET_DB_FILE_OK,'%s|0' % message_key)
            client_id.sendall(msg)
    except:
        msg = protocol.message(protocol.CONFIG_SET_DB_FILE_FAILED,
                               '%s|%s' % (message_key,traceback.format_exc()))
        client_id.sendall(msg)

def _send_posix_mq_connection(client_id,client_hostname):
    ok_flag = False
    try:
        if(posix_ipc is not None and
           not isinstance(client_id,posix_ipc.MessageQueue)):
            if client_hostname == socket.gethostname(): # same host
                #open a message queue
                new_mq = _PosixQueue()
                client_id._pmq = new_mq
                mq_name = new_mq.names()
                ok_flag = True
    except:
        import traceback
        traceback.print_exc()
    finally:
        if ok_flag:
            client_id.sendall(protocol.message(protocol.POSIX_MQ_OK,'|'.join(mq_name)))
            return new_mq
        else:
            client_id.sendall(protocol.message(protocol.POSIX_MQ_FAILED))

def _send_unknow_message(client_id):
    client_id.sendall(protocol.message(protocol.UNKNOW_MESSAGE))

def _client_rx(client):
    tcp_data = ''
    posix_queue_data = ''
    posix_queue = None
    r_listen = [client]
    try:
        stopFlag = False
        while not stopFlag:
            r,_,_ = select.select(r_listen,[],[])
            for fd in r:
                if fd == client: # tcp
                    try:
                        raw_data = client.recv(16 * 1024)
                    except:
                        raw_data = None

                    if raw_data:
                        tcp_data = '%s%s' % (tcp_data,raw_data)
                    else:
                        stopFlag = True
                        break

                    data = tcp_data
                    c_id = client
                else:
                    posix_queue_data = '%s%s' % (posix_queue_data,posix_queue.receive()[0])
                    data = posix_queue_data
                    c_id = posix_queue

                while data:
                    try:
                        messageType,message,data = protocol.unpack_message(data)
                        if messageType == protocol.LOCK:
                            lock_objects = message.split('|')
                            prio = int(lock_objects.pop(0))
                            _lock(c_id,prio,lock_objects,message)
                        elif messageType == protocol.UNLOCK:
                            lock_objects = message.split('|')
                            prio = int(lock_objects.pop(0))
                            _unlock(c_id,prio,lock_objects)
                        elif messageType == protocol.REDIS_QUERY:
                            _send_redis_info(c_id)
                        elif messageType == protocol.POSIX_MQ_QUERY:
                            posix_queue = _send_posix_mq_connection(c_id,message)
                            if posix_queue:
                                r,_,_ = select.select([posix_queue.mqd],[],[],10.)
                                posix_queue.unlink()
                                if r:
                                    raw_data = posix_queue.receive()[0]
                                    messageType,message,raw_data = protocol.unpack_message(raw_data)
                                    if messageType != protocol.POSIX_MQ_OPENED:
                                        raise RuntimeError("Client didn't send open message")
                                else:
                                    raise RuntimeError("Client didn't send open message before timeout")
                                r_listen.insert(0,posix_queue.mqd)
                        elif messageType == protocol.CONFIG_GET_FILE:
                            _send_config_file(c_id,message)
                        elif messageType == protocol.CONFIG_GET_DB_BASE_PATH:
                            _send_config_db_files(c_id,message)
                        elif messageType == protocol.CONFIG_SET_DB_FILE:
                            _write_config_db_file(c_id,message)
                        else:
                            _send_unknow_message(c_id)
                    except ValueError:
                        import traceback
                        traceback.print_exc()
                        break
                    except:
                        import traceback
                        traceback.print_exc()
                        print 'Error with client id %s, close it' % client
                        raise

                if fd == client:
                    tcp_data = data
                else:
                    posix_queue_data = data
    except:
        import traceback
        traceback.print_exc()
        pass
    finally:
        _clean(client)
        client.close()
        if posix_queue:
            posix_queue.close()
            _clean(posix_queue)

def sigterm_handler(_signo, _stack_frame):
    # On signal received, close the signal pipe to do a clean exit.
    os.close(sig_write)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db_path",dest="db_path",default="./db",
                        help="database path")
    parser.add_argument("--redis_port",dest="redis_port",default=6379,type=int,
                        help="redis connection port")
    parser.add_argument("--posix_queue",dest="posix_queue",type=int,default=1,
                        help="enable/disable posix_queue connection")
    parser.add_argument("--port",dest="port",type=int,default=0,
                        help="server port (default to 0: take a free port)")
    parser.add_argument("--tango_port",dest="tango_port",type=int,default=0,
                        help="tango server port (default to 0: disable)")
    parser.add_argument("--tango_debug_level",dest="tango_debug_level",type=int,default=0,
                        help="tango debug level (default to 0: WARNING,1:INFO,2:DEBUG)")
    global _options
    _options = parser.parse_args()

    # Binds system signals.
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    # pimp my path
    _options.db_path = os.path.abspath(os.path.expanduser(_options.db_path))

    #posix queues
    if not _options.posix_queue:
        global posix_ipc
        posix_ipc = None

    #broadcast
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp.bind(("",protocol.DEFAULT_UDP_SERVER_PORT))

    #tcp
    connectedFlag = False
    tcp = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    tcp.bind(("",_options.port))
    port = tcp.getsockname()[1]
    tcp.listen(512)        # limit to 512 clients

    #Tango databaseds
    if _options.tango_port > 0:
        print '[TANGO] Database started on port:',_options.tango_port
        tango_rp,tango_wp = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            os.close(tango_rp)
            os.dup2(tango_wp,sys.stdout.fileno())
            os.dup2(tango_wp,sys.stderr.fileno())
            os.close(tango_wp)
            start_database_ds(tango_port = _options.tango_port,debug_level = _options.tango_debug_level)
            sys.exit(0)
        else:
            os.close(tango_wp)
    else:
        tango_rp = None

    #start redis
    rp,wp = os.pipe()
    redis_process = subprocess.Popen(['redis-server',redis_conf.get_redis_config_path(),
                                      '--port','%d' % _options.redis_port],
                                     stdout=wp,stderr=subprocess.STDOUT,cwd=_options.db_path)
    # signal pipe
    global sig_write
    sig_read, sig_write = os.pipe()

    try:
      fd_list = [udp,tcp,rp,sig_read]
      if tango_rp:
          fd_list.append(tango_rp)
      msg_prefix = {tango_rp:'[TANGO]',
                    rp:'[REDIS]'}

      bosse = True

      while bosse:
        rlist,_,_ = select.select(fd_list,[],[],-1)

        for s in rlist:
            if s == udp:
                buff,address = udp.recvfrom(8192)
                if buff.find('Hello') > -1:
                    udp.sendto('%s|%d' % (socket.gethostname(),port),address)

            elif s == tcp:
                newSocket, addr = tcp.accept()
                newSocket.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)

                gevent.spawn(_client_rx,newSocket)

            elif s == sig_read:
                bosse = False
                break
            else:
                msg = os.read(s,8192)
                if msg:
                    print '%s: %s' % (msg_prefix.get(s,'[DEFAULT]'),msg)
                else:
                    fd_list.remove(tango_rp)
                    os.close(tango_rp)
                    print '%s: Warning Database exit' % (msg_prefix.get(s,'[DEFAULT]'))
                break
    except KeyboardInterrupt:
        pass
    finally:
        redis_process.terminate()

if __name__ == "__main__" and __package__ is None:
    main()
