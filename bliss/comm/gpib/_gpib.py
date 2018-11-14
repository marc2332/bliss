# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

__all__ = [
    "EnetSocket",
    "Enet",
    "Prologix",
    "TangoGpib",
    "Gpib",
    "to_tmo",
    "TMO_MAP",
    "GpibError",
    "GpibTimeout",
    "EnetError",
    "PrologixError",
]

import re
import logging
import gevent
from gevent import lock
import numpy
from .libnienet import EnetSocket
from ..tcp import Socket
from ..exceptions import CommunicationError, CommunicationTimeout
from ...common.greenlet_utils import KillMask, protect_from_kill

from bliss.common.utils import OrderedDict
from bliss.common.tango import DeviceProxy

__TMO_TUPLE = (
    0.,
    10E-6,
    30E-6,
    100E-6,
    300E-6,
    1E-3,
    3E-3,
    10E-3,
    30E-3,
    100E-3,
    300E-3,
    1.,
    3.,
    10.,
    30.,
    100.,
    300.,
    1E3,
)

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


class GpibError(CommunicationError):
    pass


class GpibTimeout(CommunicationTimeout):
    pass


class EnetError(GpibError):
    pass


class Enet(EnetSocket):
    def __init__(self, cnt, **keys):
        EnetSocket.__init__(self, None)  # Don't use the socket connection
        url = keys.pop("url")
        url_parse = re.compile("^(enet://)?([^:/]+):?([0-9]*)$")
        match = url_parse.match(url)
        if match is None:
            raise EnetError("Enet: url is not valid (%s)" % url)
        self._host = match.group(2)
        self._port = match.group(3) and int(match.group(3)) or 5000
        self._sock = Socket(self._host, self._port, timeout=keys.get("timeout"))
        self._gpib_kwargs = keys

    def init(self):
        if self._sock._fd is None:
            self.ibdev(
                pad=self._gpib_kwargs.get("pad"),
                sad=self._gpib_kwargs.get("sad"),
                tmo=self._gpib_kwargs.get("tmo"),
            )

    def close(self):
        self._sock.close()

    def _open(self):
        pass

    def _send(self, string):
        self._sock.write(string)
        return len(string)

    def _recv(self, length):
        return self._sock.read(length)


class PrologixError(GpibError):
    pass


class Prologix:
    def __init__(self, cnt, **keys):
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug
        url = keys.pop("url")
        url_parse = re.compile("^(prologix://)?([^:/]+):?([0-9]*)$")
        match = url_parse.match(url)
        if match is None:
            raise PrologixError("Inet: url is not valid (%s)" % url)
        hostname = match.group(2)
        port = match.group(3) and int(match.group(3)) or 1234
        self._debug("Prologix::__init__() host = %s port = %s" % (hostname, port))
        self._sock = Socket(hostname, port, timeout=keys.get("timeout"))
        self._gpib_kwargs = keys

    def init(self):
        self._debug("Prologix::init()")
        if self._sock._fd is None:
            # the Prologix must be a controller (mode 1)
            self._debug("Prologix::init(): set to mode 1 (Controller) ")
            self._sock.write("++mode 1\n")
            self._sock.write("++clr\n")
            self._debug("Prologix::init() save the configuration set to 0")
            self._sock.write("++savecfg 0\n")
            self._debug("Prologix::init() auto (read_after_write) set to 0")
            self._sock.write("++auto 0\n")

            self._eos = self._gpib_kwargs["eos"]
            if self._eos == "\r\n":
                self._debug(
                    "Prologix::init() eos set to 0 (%s)" % [ord(c) for c in self._eos]
                )
                self._sock.write("++eos 0\n")
            elif self._eos == "\r":
                self._debug("Prologix::init() eos set to 1 (%s)" % self._eos)
                self._sock.write("++eos 1\n")
            elif self._eos == "\n":
                self._debug("Prologix::init() eos set to 2 (%s)" % self._eos)
                self._sock.write("++eos 2\n")
            else:
                self._debug("Prologix::init() eos set to 3 (%s)" % self._eos)
                self._sock.write("++eos 3\n")

            self._debug("Prologix::init() eoi set to 1")
            self._sock.write("++eoi 1\n")
            self._debug("Prologix::init() read_tmo_ms set to 13")
            self._sock.write("++read_tmo_ms 13\n")
            # the gpib address
            self._sad = self._gpib_kwargs.get("sad", 0)
            self._pad = self._gpib_kwargs["pad"]
            if self._sad == 0:
                self._debug(
                    "Prologix::init() gpib primary address set to %d" % self._pad
                )
                self._sock.write("++addr %d\n" % self._pad)
            else:
                self._debug(
                    "Prologix::init() gpib primary & secondary address' set to %d:%d"
                    % (self._pad, self._sad)
                )
                self._sock.write("++addr %d %d\n" % (self._pad, self._sad))

    def close(self):
        self._sock.close()

    def _open(self):
        pass

    """
    Prologix commands start with ++. The characters <CR> <LF> <ESC> and <+>
    are therefore protected by adding <ESC> before each character so that the Prologix 
    does not interpret them.
    """

    def ibwrt(self, cmd):
        self._debug("Sent: %s" % cmd)
        cmd = (
            cmd.replace("\33", "\33" + "\33")
            .replace("+", "\33" + "+")
            .replace("\10", "\33" + "\10")
            .replace("\13", "\33" + "\13")
        )
        self._sock.write(cmd + "\n")
        return len(cmd)

    def ibrd(self, length):
        self._sock.write("++read EOI\n")
        return self._sock.raw_read(maxsize=length)

    def _raw(self, length):
        return self.ibrd(length)


def TangoGpib(cnt, **keys):
    from PyTango import GreenMode
    from PyTango.client import Object

    return Object(keys.pop("url"), green_mode=GreenMode.Gevent)


class TangoDeviceServer:
    def __init__(self, cnt, **keys):
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug
        url = keys.pop("url")
        url_tocken = "tango_gpib_device_server://"
        if not url.startswith(url_tocken):
            raise GpibError("Tango_Gpib_Device_Server: url is not valid (%s)" % url)
        self._tango_url = url[len(url_tocken) :]
        self.name = self._tango_url
        self._proxy = None
        self._gpib_kwargs = keys
        self._pad = keys["pad"]
        self._sad = keys.get("sad", 0)
        self._pad_sad = self._pad + (self._sad << 8)

    def init(self):
        self._debug("TangoDeviceServer::init()")
        if self._proxy is None:
            self._proxy = DeviceProxy(self._tango_url)

    def close(self):
        self._proxy = None

    def ibwrt(self, cmd):
        self._debug("Sent: %s" % cmd)
        ncmd = numpy.zeros(4 + len(cmd), dtype=numpy.uint8)
        ncmd[3] = self._pad
        ncmd[2] = self._sad
        ncmd[4:] = [ord(x) for x in cmd]
        self._proxy.SendBinData(ncmd)

    def ibrd(self, length):
        self._proxy.SetTimeout([self._pad_sad, self._gpib_kwargs.get("tmo", 12)])
        msg = self._proxy.ReceiveBinData([self._pad_sad, length])
        self._debug("Received: %s" % msg)
        return msg.tostring()

    def _raw(self, length):
        return self.ibrd(length)


class LocalGpibError(GpibError):
    pass


class LocalGpib(object):

    URL_RE = re.compile("^(local://)?([0-9]{1,2})$")

    def __init__(self, cnt, **keys):
        url = keys.pop("url")
        match = self.URL_RE.match(url)
        if match is None:
            raise LocalGpibError("LocalGpib: url is not valid (%s)" % url)
        self.board_index = int(match.group(2))
        if self.board_index < 0 or self.board_index > 15:
            raise LocalGpibError("LocalGpib: url is not valid (%s)" % url)
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug
        self._gpib_kwargs = keys

    def __str__(self):
        return "{0}(board={1})".format(type(self).__name__, self.board_index)

    def init(self):
        self._debug("init()")
        opts = self._gpib_kwargs
        from . import libgpib

        self.gpib = libgpib
        self._debug("libgpib version %s", self.gpib.ibvers())
        self.gpib.GPIBError = LocalGpibError
        self.ud = self.gpib.ibdev(
            self.board_index, pad=opts["pad"], sad=opts["sad"], tmo=opts["tmo"]
        )

    def ibwrt(self, cmd):
        self._debug("Sent: %r" % cmd)
        tp = gevent.get_hub().threadpool
        return tp.spawn(self.gpib.ibwrt, self.ud, cmd).get()

    def ibrd(self, length):
        tp = gevent.get_hub().threadpool
        return tp.spawn(self.gpib.ibrd, self.ud, length).get()

    def ibtmo(self, tmo):
        return self.gpib.ibtmo(self.ud, tmo)

    def close(self):
        pass


def try_open(fu):
    def rfunc(self, *args, **keys):
        with KillMask():
            self.open()
        timeout = keys.get("timeout")
        if timeout and self._timeout != timeout:
            if gpib_type != self.PROLOGIX:
                with KillMask():
                    self._raw_handler.ibtmo(timeout)
            self._timeout = timeout
        with KillMask():
            try:
                return fu(self, *args, **keys)
            except:
                try:
                    self.close()
                except:
                    pass
                raise

    return rfunc


class Gpib:
    """Gpib object

    from bliss.comm.gpib import Gpib
    interface = Gpib(url="enet://gpibid00a.esrf.fr", pad=15)
    """

    ENET, TANGO, TANGO_DEVICE_SERVER, PROLOGIX, LOCAL = list(range(5))
    READ_BLOCK_SIZE = 64 * 1024

    def __init__(self, url=None, pad=0, sad=0, timeout=1., tmo=13, eot=1, eos="\n"):

        self._gpib_kwargs = {
            "url": url,
            "pad": pad,
            "sad": sad,
            "tmo": tmo,
            "timeout": timeout,
            "eos": eos,
        }

        self._eos = eos
        self._timeout = timeout
        self._lock = lock.RLock()
        self._raw_handler = None
        self._logger = logging.getLogger(str(self))
        self._debug = self._logger.debug
        self.gpib_type = self.ENET
        self._data = ""

    @property
    def lock(self):
        return self._lock

    def open(self):
        if self._raw_handler is None:
            self.gpib_type = self._check_type()
            if self.gpib_type == self.ENET:
                self._raw_handler = Enet(self, **self._gpib_kwargs)
                self._raw_handler.init()
            elif self.gpib_type == self.PROLOGIX:
                self._raw_handler = Prologix(self, **self._gpib_kwargs)
                self._raw_handler.init()
            elif self.gpib_type == self.TANGO:
                self._raw_handler = TangoGpib(self, **self._gpib_kwargs)
            elif self.gpib_type == self.TANGO_DEVICE_SERVER:
                self._raw_handler = TangoDeviceServer(self, **self._gpib_kwargs)
                self._raw_handler.init()
            elif self.gpib_type == self.LOCAL:
                self._raw_handler = LocalGpib(self, **self._gpib_kwargs)
                self._raw_handler.init()

    def close(self):
        if self._raw_handler is not None:
            self._raw_handler.close()
            self._raw_handler = None

    @try_open
    def raw_read(self, maxsize=None, timeout=None):
        size_to_read = maxsize or self.READ_BLOCK_SIZE
        return self._raw_handler.ibrd(size_to_read)

    def read(self, size=1, timeout=None):
        with self._lock:
            return self._read(size)

    @try_open
    def _read(self, size=1):
        return self._raw_handler.ibrd(size)

    def readline(self, eol=None, timeout=None):
        with self._lock:
            return self._readline(eol)

    @try_open
    def _readline(self, eol):
        local_eol = eol or self._eos
        url = self._gpib_kwargs.get("url")
        pad = self._gpib_kwargs.get("pad")
        timeout_errmsg = "timeout on gpib(%s,%d)" % (url, pad)
        with gevent.Timeout(self._timeout, GpibTimeout(timeout_errmsg)):
            eol_pos = self._data.find(local_eol)
            while eol_pos == -1:
                self._data += self._raw_handler.ibrd(self.READ_BLOCK_SIZE)
                eol_pos = self._data.find(local_eol)
        msg = self._data[:eol_pos]
        self._data = self._data[eol_pos + len(local_eol) :]
        return msg

    def write(self, msg, timeout=None):
        with self._lock:
            return self._write(msg)

    @try_open
    def _write(self, msg):
        return self._raw_handler.ibwrt(msg)

    @protect_from_kill
    def write_read(self, msg, write_synchro=None, size=1, timeout=None):
        with self._lock:
            self._write(msg)
            if write_synchro:
                write_synchro.notify()
            return self._read(size)

    @protect_from_kill
    def write_readline(self, msg, write_synchro=None, eol=None, timeout=None):
        with self._lock:
            self._write(msg)
            if write_synchro:
                write_synchro.notify()
            return self._readline(eol)

    @protect_from_kill
    def write_readlines(
        self, msg, nb_lines, write_synchro=None, eol=None, timeout=None
    ):
        with self._lock:
            self._write(msg)
            if write_synchro:
                write_synchro.notify()
            r_lines = []
            for i in range(nb_lines):
                r_lines.append(self._readline(eol))
        return r_lines

    def flush(self):
        self._raw_handler = None

    def _check_type(self):
        url = self._gpib_kwargs.get("url", "")
        url_lower = url.lower()
        if url_lower.startswith("enet://"):
            return self.ENET
        elif url_lower.startswith("prologix://"):
            return self.PROLOGIX
        elif url_lower.startswith("tango://"):
            return self.TANGO
        elif url_lower.startswith("tango_gpib_device_server://"):
            return self.TANGO_DEVICE_SERVER
        elif url_lower.startswith("local://"):
            return self.LOCAL
        else:
            return None

    def __str__(self):
        opts = self._gpib_kwargs
        return "{0}(url={1}, pad={2})".format(
            self.__class__.__name__, opts["url"], opts["pad"]
        )
