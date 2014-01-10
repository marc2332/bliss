import gevent
from gevent import socket,select,event
import time

def try_connect(fu) :
    def rfunc(self,*args,**kwarg) :
        write_func = fu.func_name.startswith('write')
        if(not self._connected and (not self._data or write_func)) :
            self.connect()

        if not self._connected:
            prev_timeout = kwarg.get('timeout',None)
            kwarg.update({'timeout':0.})
            try:
                return fu(self,*args,**kwarg)
            except RuntimeError:
                self.connect()
                kwarg.update({'timeout':prev_timeout})
        return fu(self,*args,**kwarg)
    return rfunc

class Socket:
    def __init__(self,host,port,
                 eol='\n',      # end of line for each rx message
                 timeout=5.,    # default timeout for read write
                 ) :
        self._host = host
        self._port = port
        self._fd = None
        self._timeout = timeout
        self._connected = False
        self._eol = eol
        self._data = ''
        self._event = event.Event()
        self._raw_read_task = None

    def connect(self,host = None,port = None) :
        local_host = host or self._host
        local_port = port or self._port

        if self._connected: 
            self._fd.close()
            if self._raw_read_task:
                self._raw_read_task.join()
                self._raw_read_task = None

        self._fd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._fd.connect((local_host,local_port))
        self._fd.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._connected = True
        self._host = local_host
        self._port = local_port
        self._data = ''
        self._raw_read_task = gevent.spawn(self._raw_read)
        return True

    def close(self) :
        if self._connected:
            self._fd.close()
            if self._raw_read_task:
                self._raw_read_task.join()
                self._raw_read_task = None
            self._data = ''

    @try_connect
    def raw_read(self,maxsize = None,timeout = None) :
        local_timeout = timeout or self._timeout
        start_time = time.time()
        while not self._data:
            if not self._event.wait(local_timeout) :
                raise RuntimeError("raw_read timeout on socket (%s,%d)" % 
                                   (self._host,self._port))
            elapsed_time = time.time() - start_time
            local_timeout -= elapsed_time
            self._event.clear()
        if maxsize:
            msg = self._data[:maxsize]
            self._data = self._data[maxsize + 1:]
        else:
            msg = self._data
            self._data = ''
        return msg

    @try_connect
    def read(self,size=1,timeout=None):
        local_timeout = timeout or self._timeout
        start_time = time.time()
        while len(self._data) < size:
            if not self._event.wait(local_timeout):
                raise RuntimeError("read timeout on socket (%s,%d)" % 
                                   (self._host,self._port))
            elapsed_time = time.time() - start_time
            local_timeout -= elapsed_time
            if local_timeout < 0: local_timeout = 0.
            self._event.clear()
        msg = self._data[:size]
        self._data = self._data[size + 1:]
        return msg

    @try_connect
    def readline(self,eol = None,timeout=None) :
        local_timeout = timeout or self._timeout
        local_eol = eol or self._eol
        start_time = time.time()
        eol_pos = self._data.find(local_eol)
        while eol_pos == -1:
            if not self._event.wait(local_timeout):
                raise RuntimeError("readline timeout on socket (%s,%d)" % 
                                   (self._host,self._port))
            elapsed_time = time.time() - start_time
            local_timeout -= elapsed_time
            if local_timeout < 0: local_timeout = 0.
            eol_pos = self._data.find(local_eol)
            self._event.clear()

        msg = self._data[:eol_pos]
        self._data = self._data[eol_pos + 1:]
        return msg

    @try_connect
    def write(self,msg,timeout=None) :
        self._fd.sendall(msg,timeout=timeout)

    @try_connect
    def write_read(self,msg,write_synchro = None,size=1,timeout=None) :
        self._fd.sendall(msg)
        if write_synchro: write_synchro.notify()
        return self.read(size=size,timeout=timeout)
    
    @try_connect
    def write_readline(self,msg,write_synchro = None,eol = None,timeout = None):
        with gevent.Timeout(timeout or self._timeout, RuntimeError("write_readline timed out")):
            self._fd.sendall(msg)
            if write_synchro:write_synchro.notify()
            return self.readline(eol=eol,timeout=timeout)

    def flush(self) :
        self._data = ''

    def _raw_read(self) :
        try:
            while(1):
                raw_data = self._fd.recv(16*1024)
                if raw_data:
                    self._data += raw_data
                    self._event.set()
                else:
                    break
        except: pass
        finally:
            self._connected = False
            self._fd.close()
            self._fd = None


