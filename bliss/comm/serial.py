import serial
from gevent import socket

def try_open(fu) :
    def rfunc(self,*args,**kwarg) :
        self.open()
        timeout = kwarg.get('timeout',None)
        try:
            if timeout:
                self._raw_handler.setTimeout(timeout)
            return fu(self,*args,**kwarg)
        finally:
            if timeout:
                self._raw_handler.setTimeout(self._timeout)
    return rfunc

class Serial:
    LOCAL,RFC2217 = range(2)

    def __init__(port=None, 
                 baudrate=9600,
                 bytesize=EIGHTBITS,
                 parity=PARITY_NONE,
                 stopbits=STOPBITS_ONE, 
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
        
    def open(self) :
        if self._raw_handler is None:
            serial_type = self._check_type()
            if serial_type == self.RFC2217:
                pass
            else:                   # LOCAL
                self._raw_handler = serial.Serial(**self._serial_kwargs)
        
    def close(self) :
        self._raw_handler = None
        
    @try_open
    def raw_read(self,maxsize = None,timeout = None) :
        if maxsize:
            return self._raw_handler.read(size=maxsize)
        else:
            return self._raw_handler.read()
                
    @try_open
    def read(self,size=1,timeout=None):
        msg = self._raw_handler.read(size=size)
        if len(msg) != size:
            raise RuntimeError("read timeout on serial (%s)" % self._serial_kwargs.get(port,''))
        return msg

    @try_open
    def readline(self,eol = None,timeout = None) :
        local_eol = eol or self._eol
        return self._raw_handler.readline(eol = local_eol)
    
    @try_open
    def write(self,msg,timeout=None) :
        return self._raw_handler.write(msg)
        
    @try_open
    def write_read(self,msg,write_synchro=None,size=1,timeout=None) :
        self._raw_handler.write(msg)
        if write_synchro: write_synchro.notify()
        return self.read(size=size)

    @try_open
    def write_readline(self,msg,write_synchro = None,
                       eol = None,timeout = None) :
        self._raw_handler.write(msg)
        if write_synchro: write_synchro.notify()
        return self.readline(eol=eol)

    def flush(self) :
        if self._raw_handler:
            self._raw_handler.flushInput()

    def _check_type(self) :
        port = self._serial_kwargs.get(port,'')
        if port.lower().startswith("rfc2217://"):
            return self.RFC2217
        else:
            return self.LOCAL
