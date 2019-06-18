# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
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
import enum
import gevent
from gevent import lock
import numpy
from .libnienet import EnetSocket
from ..tcp import Socket
from ..exceptions import CommunicationError, CommunicationTimeout
from ...common.greenlet_utils import KillMask, protect_from_kill
from bliss.comm.util import HexMsg

from bliss.common.tango import DeviceProxy
from bliss.common import session
from bliss.common.logtools import LogMixin

__TMO_TUPLE = (
    0.0,
    10e-6,
    30e-6,
    100e-6,
    300e-6,
    1e-3,
    3e-3,
    10e-3,
    30e-3,
    100e-3,
    300e-3,
    1.0,
    3.0,
    10.0,
    30.0,
    100.0,
    300.0,
    1e3,
)

TMO_MAP = dict([(tmo, t) for tmo, t in enumerate(__TMO_TUPLE)])


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
        url_parse = re.compile(r"^(enet://)?([^:/]+):?([0-9]*)$")
        match = url_parse.match(url)
        if match is None:
            raise EnetError("Enet: url is not valid (%s)" % url)
        self._host = match.group(2)
        self._port = match.group(3) and int(match.group(3)) or 5000
        self._sock = Socket(self._host, self._port, timeout=keys.get("timeout"))
        self._gpib_kwargs = keys

    def init(self):
        if not self._sock._connected:
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


class Prologix(LogMixin):
    def __init__(self, cnt, **keys):
        url = keys.pop("url")
        url_parse = re.compile(r"^(prologix://)?([^:/]+):?([0-9]*)$")
        match = url_parse.match(url)
        if match is None:
            raise PrologixError("Inet: url is not valid (%s)" % url)
        hostname = match.group(2)
        port = match.group(3) and int(match.group(3)) or 1234
        self._sock = Socket(hostname, port, timeout=keys.get("timeout"))
        session.get_current().map.register(self, children_list=["comms", self._sock])
        self._logger.debug(f"Prologix::__init__() host = {hostname} port = {port}")
        self._gpib_kwargs = keys

    def init(self):
        self._logger.debug("Prologix::init()")
        if not self._sock._connected:
            # the Prologix must be a controller (mode 1)
            self._logger.debug("Prologix::init(): set to mode 1 (Controller) ")
            self._sock.write(b"++mode 1\n")
            self._sock.write(b"++clr\n")
            self._logger.debug("Prologix::init() save the configuration set to 0")
            self._sock.write(b"++savecfg 0\n")
            self._logger.debug("Prologix::init() auto (read_after_write) set to 0")
            self._sock.write(b"++auto 0\n")

            self._eol = self._gpib_kwargs["eol"]
            if self._eol == "\r\n":
                self._logger.debug_data("Prologix::init() eos set to 0 (%s)", self._eol)
                self._sock.write(b"++eos 0\n")
            elif self._eol == "\r":
                self._logger.debug("Prologix::init() eos set to 1 (%s)" % self._eol)
                self._sock.write(b"++eos 1\n")
            elif self._eol == "\n":
                self._logger.debug("Prologix::init() eos set to 2 (%s)" % self._eol)
                self._sock.write(b"++eos 2\n")
            else:
                self._logger.debug("Prologix::init() eos set to 3 (%s)" % self._eol)
                self._sock.write(b"++eos 3\n")

            self._logger.debug("Prologix::init() eoi set to 1")
            self._sock.write(b"++eoi 1\n")
            self._logger.debug("Prologix::init() read_tmo_ms set to 13")
            self._sock.write(b"++read_tmo_ms 13\n")
            # the gpib address
            self._sad = self._gpib_kwargs.get("sad", 0)
            self._pad = self._gpib_kwargs["pad"]
            if self._sad == 0:
                self._logger.debug(
                    "Prologix::init() gpib primary address set to %d" % self._pad
                )
                self._sock.write(b"++addr %d\n" % self._pad)
            else:
                self._logger.debug(
                    "Prologix::init() gpib primary & secondary address' set to %d:%d"
                    % (self._pad, self._sad)
                )
                self._sock.write(b"++addr %d %d\n" % (self._pad, self._sad))

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
        self._logger.debug("Sent: %s" % cmd)
        cmd = (
            cmd.replace(b"\33", b"\33" + b"\33")
            .replace(b"+", b"\33" + b"+")
            .replace(b"\10", b"\33" + b"\10")
            .replace(b"\13", b"\33" + b"\13")
        )
        self._sock.write(cmd + b"\n")
        return len(cmd)

    def ibrd(self, length):
        self._sock.write(b"++read EOI\n")
        return self._sock.raw_read(maxsize=length)

    def _raw(self, length):
        return self.ibrd(length)


def TangoGpib(cnt, **keys):
    from PyTango import GreenMode
    from PyTango.client import Object

    return Object(keys.pop("url"), green_mode=GreenMode.Gevent)


class TangoDeviceServer(LogMixin):
    def __init__(self, cnt, **keys):
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
        session.get_current().map.register(self)

    def init(self):
        self._logger.debug("TangoDeviceServer::init()")
        if self._proxy is None:
            self._proxy = DeviceProxy(self._tango_url)

    def close(self):
        self._proxy = None

    def ibwrt(self, cmd):
        self._logger.debug("Sent: %s" % cmd)
        ncmd = numpy.zeros(4 + len(cmd), dtype=numpy.uint8)
        ncmd[3] = self._pad
        ncmd[2] = self._sad
        ncmd[4:] = [x for x in cmd]
        self._proxy.SendBinData(ncmd)

    def ibrd(self, length):
        self._proxy.SetTimeout([self._pad_sad, self._gpib_kwargs.get("tmo", 12)])
        msg = self._proxy.ReceiveBinData([self._pad_sad, length])
        self._logger.debug("Received: %s" % msg)
        return msg.tostring()

    def _raw(self, length):
        return self.ibrd(length)


class LocalGpibError(GpibError):
    pass


class LocalGpib(LogMixin):

    URL_RE = re.compile(r"^(local://)?([0-9]{1,2})$")

    def __init__(self, cnt, **keys):
        url = keys.pop("url")
        match = self.URL_RE.match(url)
        if match is None:
            raise LocalGpibError("LocalGpib: url is not valid (%s)" % url)
        self.board_index = int(match.group(2))
        if self.board_index < 0 or self.board_index > 15:
            raise LocalGpibError("LocalGpib: url is not valid (%s)" % url)

        self._gpib_kwargs = keys
        session.get_current().map.register(self, tag=str(self))

    def __str__(self):
        return "{0}(board={1})".format(type(self).__name__, self.board_index)

    def init(self):
        self._logger.debug("init()")
        opts = self._gpib_kwargs
        from . import libgpib

        self.gpib = libgpib
        self._logger.debug("libgpib version %s", self.gpib.ibvers())
        self.gpib.GPIBError = LocalGpibError
        self.ud = self.gpib.ibdev(
            self.board_index, pad=opts["pad"], sad=opts["sad"], tmo=opts["tmo"]
        )

    def ibwrt(self, cmd):
        self._logger.debug("Sent: %r" % cmd)
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


class Gpib(LogMixin):
    """Gpib object

    from bliss.comm.gpib import Gpib
    interface = Gpib(url="enet://gpibid00a.esrf.fr", pad=15)
    """

    @enum.unique
    class GpibType(enum.IntEnum):
        ENET = 0
        TANGO = 1
        TANGO_DEVICE_SERVER = 2
        PROLOGIX = 3
        LOCAL = 4

    READ_BLOCK_SIZE = 64 * 1024

    def __init__(self, url=None, pad=0, sad=0, timeout=1.0, tmo=13, eot=1, eol="\n"):

        self._gpib_kwargs = {
            "url": url,
            "pad": pad,
            "sad": sad,
            "tmo": tmo,
            "timeout": timeout,
            "eol": eol,
        }

        self._eol = eol
        self._timeout = timeout
        self._lock = lock.RLock()
        self._raw_handler = None

        self._data = b""
        session.get_current().map.register(self, tag=str(self))

    def __str__(self):
        opts = self._gpib_kwargs
        return "{0}[{1}:{2}]".format(self.__class__.__name__, opts["url"], opts["pad"])

    @property
    def lock(self):
        return self._lock

    @property
    def gpib_type(self):
        return self._check_type()

    def open(self):
        if self._raw_handler is None:
            self._logger.debug(f"opening {self.gpib_type} gpib")
            self._logger.debug(self._logger.log_format_dict(self._gpib_kwargs))
            if self.gpib_type == Gpib.GpibType.ENET:
                self._raw_handler = Enet(self, **self._gpib_kwargs)
                self._raw_handler.init()
            elif self.gpib_type == Gpib.GpibType.PROLOGIX:
                self._raw_handler = Prologix(self, **self._gpib_kwargs)
                self._raw_handler.init()
            elif self.gpib_type == Gpib.GpibType.TANGO:
                self._raw_handler = TangoGpib(self, **self._gpib_kwargs)
            elif self.gpib_type == Gpib.GpibType.TANGO_DEVICE_SERVER:
                self._raw_handler = TangoDeviceServer(self, **self._gpib_kwargs)
                self._raw_handler.init()
            elif self.gpib_type == Gpib.GpibType.LOCAL:
                self._raw_handler = LocalGpib(self, **self._gpib_kwargs)
                self._raw_handler.init()

    def close(self):
        if self._raw_handler is not None:
            self._raw_handler.close()
            self._raw_handler = None
            self._logger.debug("close")

    @try_open
    def raw_read(self, maxsize=None, timeout=None):
        size_to_read = maxsize or self.READ_BLOCK_SIZE
        msg = self._raw_handler.ibrd(size_to_read)
        self._logger.debug_data("raw_read", msg)
        return msg

    def read(self, size=1, timeout=None):
        with self._lock:
            return self._read(size)

    @try_open
    def _read(self, size=1):
        msg = self._raw_handler.ibrd(size)
        self._logger.debug_data("read", msg)
        return msg

    def readline(self, eol=None, timeout=None):
        with self._lock:
            return self._readline(eol)

    @try_open
    def _readline(self, eol):
        local_eol = eol or self._eol
        if not isinstance(local_eol, bytes):
            local_eol = local_eol.encode()
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
        self._logger.debug_data("readline", msg)
        return msg

    def write(self, msg, timeout=None):
        with self._lock:
            return self._write(msg)

    @try_open
    def _write(self, msg):
        self._logger.debug_data("write", msg)
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
        self._logger.debug("flush")
        self._raw_handler = None

    def _check_type(self):
        url = self._gpib_kwargs.get("url", "")
        url_lower = url.lower()
        if url_lower.startswith("enet://"):
            return Gpib.GpibType.ENET
        elif url_lower.startswith("prologix://"):
            return Gpib.GpibType.PROLOGIX
        elif url_lower.startswith("tango://"):
            return Gpib.GpibType.TANGO
        elif url_lower.startswith("tango_gpib_device_server://"):
            return Gpib.GpibType.TANGO_DEVICE_SERVER
        elif url_lower.startswith("local://"):
            return Gpib.GpibType.LOCAL
        else:
            raise ValueError("Unsuported protocol %s" % url)
