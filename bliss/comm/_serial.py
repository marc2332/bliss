import gevent
from gevent import socket, select, lock, event

import serial

import weakref
import os

def try_open(fu) :
    def rfunc(self,*args,**kwarg) :
        self.open()
        return fu(self,*args,**kwarg)
    return rfunc

class LocalSerial(serial.Serial):
    def __init__(self,cnt,**keys):
        serial.Serial.__init__(self,**keys)
        self._cnt = weakref.ref(cnt)
        
        self._data = bytearray()
        self._event = event.Event()
        self._raw_read_task = gevent.spawn(self._raw_read)

    def readline(self, eol, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout, RuntimeError(timeout_errmsg)):
            local_eol = eol or self._eol
            eol_pos = self._data.find(local_eol)
            while eol_pos == -1:
                self._event.wait()
                self._event.clear()
                eol_pos = self._data.find(local_eol)

        msg = self._data[:eol_pos]
        self._data = self._data[eol_pos + len(local_eol):]
        return msg

    def read(self, size, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout,RuntimeError(timeout_errmsg)):
            while len(self._data) < size:
                self._event.wait()
                self._event.clear()
        msg = self._data[:size]
        self._data = self._data[size + 1:]
        return msg
    
    def write(self,msg,timeout) :
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout,RuntimeError(timeout_errmsg)):
            while msg:
                _,ready,_ = select.select([],[self.fd],[])
                size_send = os.write(self.fd,msg)
                msg = msg[size_send:]

    def raw_read(self, maxsize, timeout):
        timeout_errmsg = "timeout on serial(%s)" % (self._port)
        with gevent.Timeout(timeout,RuntimeError(timeout_errmsg)):
            while not self._data:
                self._event.wait()
                self._event.clear()
        if maxsize:
            msg = self._data[:maxsize]
            self._data = self._data[maxsize + 1:]
        else:
            msg = self._data
            self._data = ''
        return msg

    def flushInput(self):
        super(LocalSerial,self).flushInput()
        self._data = ''

    def _raw_read(self):
        try:
            while(1):
                ready,_,_ = select.select([self.fd],[],[])
                raw_data = os.read(self.fd,4096)
                if raw_data:
                    self._data += raw_data
                    self._event.set()
                else:
                    break
        except:
            pass
        finally:
            cnt = self._cnt()
            if cnt:
                cnt._raw_handler = None

                
class Serial:
    LOCAL,RFC2217 = range(2)

    def __init__(self,port=None, 
                 baudrate=9600,
                 bytesize=serial.EIGHTBITS,
                 parity=serial.PARITY_NONE,
                 stopbits=serial.STOPBITS_ONE, 
                 timeout=5., 
                 xonxoff=False, 
                 rtscts=False, 
                 writeTimeout=None, 
                 dsrdtr=False, 
                 interCharTimeout=None,
                 eol = '\n') :

        self._serial_kwargs = {
            "port":port,
            "baudrate":baudrate,
            "bytesize":bytesize,
            "parity":parity,
            "stopbits":stopbits,
            "timeout":timeout,
            "xonxoff":xonxoff,
            "rtscts":rtscts,
            "writeTimeout":writeTimeout,
            "dsrdtr":dsrdtr,
            "interCharTimeout":interCharTimeout,
            }
        self._eol = eol
        self._timeout = timeout
        self._raw_handler = None
        self._lock = lock.Semaphore()

    def __del__(self) :
        if self._raw_handler:
            self._raw_handler.close()

    def open(self) :
        if self._raw_handler is None:
            serial_type = self._check_type()
            if serial_type == self.RFC2217:
                pass
            else:                   # LOCAL
                self._raw_handler = LocalSerial(self,**self._serial_kwargs)
        
    def close(self) :
        if self._raw_handler:
            self._raw_handler.close()
            self._raw_handler = None
        
    @try_open
    def raw_read(self,maxsize = None,timeout = None) :
        local_timeout = timeout or self._timeout
        return self._raw_handler.raw_read(maxsize,local_timeout)
                
    @try_open
    def read(self,size=1,timeout=None):
        local_timeout = timeout or self._timeout
        msg = self._raw_handler.read(size,local_timeout)
        if len(msg) != size:
            raise RuntimeError("read timeout on serial (%s)" % self._serial_kwargs.get(port,''))
        return msg

    @try_open
    def readline(self,eol = None,timeout = None) :
        local_eol = eol or self._eol
        local_timeout = timeout or self._timeout
        return self._raw_handler.readline(local_eol,local_timeout)
    
    @try_open
    def write(self,msg,timeout=None) :
        with self._lock:
            return self._raw_handler.write(msg,timeout)
        
    @try_open
    def write_read(self,msg,write_synchro=None,size=1,timeout=None) :
        local_timeout = timeout or self._timeout
        with self._lock:
            self._raw_handler.write(msg,local_timeout)
            if write_synchro: write_synchro.notify()
            return self.read(size,local_timeout)

    @try_open
    def write_readline(self,msg,write_synchro = None,
                       eol = None,timeout = None) :
        local_eol = eol or self._eol
        local_timeout = timeout or self._timeout
        with self._lock:
            self._raw_handler.write(msg,local_timeout)
            if write_synchro: write_synchro.notify()
            return self.readline(local_eol,local_timeout)

    def flush(self) :
        if self._raw_handler:
            self._raw_handler.flushInput()

    def _check_type(self) :
        port = self._serial_kwargs.get('port','')
        if port.lower().startswith("rfc2217://"):
            return self.RFC2217
        else:
            return self.LOCAL
