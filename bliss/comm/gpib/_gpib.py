import re
import gevent
from gevent import lock
from .libnienet import EnetSocket
from ..tcp import Socket

class Enet(EnetSocket):
    def __init__(self,cnt,**keys) :
        EnetSocket.__init__(self,None) # Don't use the socket connection
        url = keys.pop('url')
        url_parse = re.compile("^(enet://)?([^:/]+):?([0-9]*)$")
        match = url_parse.match(url)
        if match is None:
            raise RuntimeError('Inet: ursl is not valid (%s)' % url)
        hostname = match.group(2)
        port = match.group(3) and int(match.group(3)) or 5000
        self._sock = Socket(hostname,port,
                            timeout = keys.get('timeout'))
        self._gpib_kwargs = keys

    def init(self) :
        if self._sock._fd is None:
            self._sock.connect()
            self.ibdev(pad = self._gpib_kwargs.get('pad'),
                       sad = self._gpib_kwargs.get('sad'),
                       tmo = self._gpib_kwargs.get('timeout'))

    def _open(self) :
        pass

    def _send(self,string) :
        self._sock.write(string)
        return len(string)

    def _recv(self,length) :
        return self._sock.read(length)


def try_open(fu) :
    def rfunc(self,*args,**keys) :
        self.open()
        self._raw_handler.init()
        timeout = keys.get('timeout')
        if timeout and self._timeout != timeout:
            self._raw_handler.ibtmo(timeout)
            self._timeout = timeout
        return fu(self,*args,**keys)
    return rfunc

class Gpib:
    ENET = range(1)
    READ_BLOCK_SIZE = 8192

    def __init__(self,url = None,pad = 0,sad = 0,timeout = 13,
                 eot = 1,eos = '\n') :
        
        self._gpib_kwargs = {
            'url'     : url,
            'pad'     : pad,
            'sad'     : sad,
            'timeout' : timeout,
            'eos'     : eos}
        
        self._eos = eos
        self._timeout = timeout
        self._lock = lock.Semaphore()
        self._raw_handler = None

    def open(self) :
        if self._raw_handler is None:
            gpib_type = self._check_type()
            if gpib_type == self.ENET:
                self._raw_handler = Enet(self,**self._gpib_kwargs)

    @try_open
    def raw_read(self,maxsize = None,timeout = None):
        size_to_read = maxsize or 1
        return self._raw_handler.ibrd(size_to_read)

    @try_open
    def read(self,size = 1,timeout = None):
        with self._lock:
            return self._raw_handler.ibrd(size)

    @try_open
    def readline(self,eol = None,timeout = None):
        with self._lock:
            return self._readline(eol)

    def _readline(self,eol):
        local_eol = eol or self._eos
        data = ''
        url = self._gpib_kwargs.get('url')
        pad = self._gpib_kwargs.get('pad')
        timeout_errmsg = "timeout on gpib(%s,%d)" % (url,pad)
        with gevent.Timeout(self._timeout,RuntimeError(timeout_errmsg)):
            data += self._raw_handler.ibrd(self.READ_BLOCK_SIZE)
            eol_pos = local_eol and data.find(local_eol) or len(data)
            while eol_pos == -1:
                data += self._raw_handler.ibrd(self.READ_BLOCK_SIZE)
                eol_pos = data.find(local_eol)
        return data[:eol_pos]

    @try_open
    def write(self,msg,timeout=None) :
        with self._lock:
            return self._raw_handler.ibwrt(msg)

    @try_open
    def write_read(self,msg,write_synchro = None,size = 1,timeout = None) :
        with self._lock:
            self._raw_handler.ibwrt(msg)
            if write_synchro: write_synchro.notify()
            return self._raw_handler.ibrd(size)

    @try_open
    def write_readline(self,msg,write_synchro = None,
                       eol = None,timeout = None) :
        with self._lock:
            self._raw_handler.ibwrt(msg)
            if write_synchro: write_synchro.notify()
            return self._readline(eol)

    def flush(self) :
        self._raw_handler = None

    def _check_type(self) :
        url = self._gpib_kwargs.get('url','')
        if url.lower().startswith("enet://") :
            return self.ENET
        else:
            return None


