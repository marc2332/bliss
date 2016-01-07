__all__ = ['EnetSocket', 'Enet', 'TangoGpib', 'Gpib', 'to_tmo', 'TMO_MAP']

import re
import logging
import gevent
from gevent import lock
from .libnienet import EnetSocket
from ..tcp import Socket

try:
    from collections import OrderedDict
except AttributeError:
    try:
        from ordereddict import OrderedDict
    except ImportError:
        OrderedDict = dict

__TMO_TUPLE = (0., 10E-6, 30E-6, 100E-6, 300E-6,
               1E-3, 3E-3, 10E-3, 30E-3, 100E-3, 300E-3,
               1., 3., 10., 30., 100., 300., 1E3,)

TMO_MAP = OrderedDict([(tmo, t) for tmo, t in enumerate(__TMO_TUPLE)])

def to_tmo(time_sec):
    """
    Returns the closest (>=) GPIB timeout constant for the given time in
    seconds.

    :param time_sec: time in seconds
    :type time_sec: int, float
    :return:
        TMO as a tuple with two elements:  TMO constant, TMO in seconds (float)
    :rtype: tuple(int, float)
    """
    for tmo, t in enumerate(__TMO_TUPLE):
        if t >= time_sec:
            return tmo, t
    return tmo, t


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
                       tmo = self._gpib_kwargs.get('tmo'))

    def close(self) :
        self._sock.close()
        
    def _open(self) :
        pass

    def _send(self,string) :
        self._sock.write(string)
        return len(string)

    def _recv(self,length) :
        return self._sock.read(length)


def TangoGpib(cnt,**keys) :
    from PyTango import GreenMode
    from PyTango.client import Object
    return Object(keys.pop('url'), green_mode=GreenMode.Gevent)


def try_open(fu) :
    def rfunc(self,*args,**keys) :
        self.open()
        timeout = keys.get('timeout')
        if timeout and self._timeout != timeout:
            self._raw_handler.ibtmo(timeout)
            self._timeout = timeout
        return fu(self,*args,**keys)
    return rfunc

class Gpib:
    ENET, TANGO = range(2)
    READ_BLOCK_SIZE = 64 * 1024

    def __init__(self,url = None,pad = 0,sad = 0,timeout = 1.,tmo = 13,
                 eot = 1,eos = '\n') :
        
        self._gpib_kwargs = {
            'url'     : url,
            'pad'     : pad,
            'sad'     : sad,
            'tmo'     : tmo,
            'timeout' : timeout,
            'eos'     : eos}
        
        self._eos = eos
        self._timeout = timeout
        self._lock = lock.Semaphore()
        self._raw_handler = None
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug

    def open(self) :
        if self._raw_handler is None:
            gpib_type = self._check_type()
            if gpib_type == self.ENET:
                self._raw_handler = Enet(self,**self._gpib_kwargs)
                self._raw_handler.init()
            elif gpib_type == self.TANGO:
                self._raw_handler = TangoGpib(self,**self._gpib_kwargs)

    def close(self) :
        if self._raw_handler is not None:
            self._raw_handler.close()
            self._raw_handler = None
            
    @try_open
    def raw_read(self,maxsize = None,timeout = None):
        size_to_read = maxsize or self.READ_BLOCK_SIZE
        return self._raw_handler.ibrd(size_to_read)

    def read(self,size = 1,timeout = None):
        with self._lock:
            return self._read(size)

    @try_open
    def _read(self,size = 1):
        return self._raw_handler.ibrd(size)

    def readline(self,eol = None,timeout = None):
        with self._lock:
            return self._readline(eol)

    @try_open
    def _readline(self,eol):
        local_eol = eol or self._eos
        data = ''
        url = self._gpib_kwargs.get('url')
        pad = self._gpib_kwargs.get('pad')
        timeout_errmsg = "timeout on gpib(%s,%d)" % (url,pad)
        with gevent.Timeout(self._timeout,RuntimeError(timeout_errmsg)):
            data += self._raw_handler.ibrd(self.READ_BLOCK_SIZE)
            if local_eol is None:
                eol_pos = len(data)
            else:
                eol_pos = data.find(local_eol)
            while eol_pos == -1:
                data += self._raw_handler.ibrd(self.READ_BLOCK_SIZE)
                eol_pos = data.find(local_eol)
        return data[:eol_pos]

    def write(self,msg,timeout=None) :
        with self._lock:
            return self._write(msg)

    @try_open
    def _write(self,msg) :
        return self._raw_handler.ibwrt(msg)

    def write_read(self,msg,write_synchro = None,size = 1,timeout = None) :
        with self._lock:
            self._write(msg)
            if write_synchro: write_synchro.notify()
            return self._read(size)

    def write_readline(self,msg,write_synchro = None,
                       eol = None,timeout = None) :
        with self._lock:
            self._write(msg)
            if write_synchro: write_synchro.notify()
            return self._readline(eol)

    def write_readlines(self,msg,nb_lines,write_synchro = None,
                        eol = None,timeout = None):
        with self._lock:
            self._write(msg)
            if write_synchro: write_synchro.notify()
            r_lines = []
            for i in range(nb_lines):
                r_lines.append(self._readline(eol))
        return r_lines
    
    def flush(self) :
        self._raw_handler = None

    def _check_type(self) :
        url = self._gpib_kwargs.get('url','')
        url_lower = url.lower()
        if url_lower.startswith("enet://") :
            return self.ENET
        elif url_lower.startswith("tango://") :
            return self.TANGO
        else:
            return None

    def __str__(self):
        opts = self._gpib_kwargs
        return "{0}(url={1}, pad={2})".format(self.__class__.__name__,
                                              opts['url'], opts['pad'])
