#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
#
# test-enet --
#
# Copyright (C) 2005 Robert Jordens <jordens@debian.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307
# USA
#
# $Id$
# arch-tag: acc2a56e-ea5d-4a47-ba55-ffacd359270b
#
# TODO:
#
#  * all the _not_impl()s
#  * non-blocking IO

import socket, sys
from struct import *
from bliss.common import session
from bliss.common.logtools import LogMixin

# debug = ["io", "ignore_not_impl"] # "dummy_io", "rw"
debug = ["ignore_not_impl"]


def _dbg(f, name=None):
    if not name:
        name = f.__name__

    def wrap(self, *a, **k):
        print("DBG: %s: enter: %s %s" % (name, repr(a), repr(k)), end=" ")
        r = f(self, *a, **k)
        print("exit: %s" % repr(r))
        return r

    wrap._dummy = True
    return wrap


def _not_impl(name):
    def wrap(self, *a, **k):
        if "ignore_not_impl" in debug:
            return None
        else:
            raise NotImplementedError("%s not implemented").with_traceback(name)

    return _dbg(wrap, name)


class EnetSocket(LogMixin):
    def __init__(self, host, port=5000):
        self._host = host
        self._port = port
        self._sock = None
        self._open()
        self.sta = self.err = self.cnt = 0
        self.enet1000 = False
        self._extra_socket = list()
        session.get_current().map.register(self, parents_list=["comms"], tag=str(self))

    def _open(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self._host, self._port))
        session.get_current().map.register(
            self, parents_list=["comms"], children_list=[self._sock], tag=str(self)
        )

    def __str__(self):
        return f"{self.__class__.__name__}={self._host}:{self._port}"

    def close(self):
        if self._sock:
            self._sock.close()
        for enet in self._extra_socket:
            enet.close()

    def _send(self, string):
        return self._sock.send(string)

    def _recv(self, length):
        s = b""
        while len(s) < length:
            s += self._sock.recv(length - len(s))
        return s

    def _close(self):
        self._sock.close()
        self._sock = None

    if "dummy_io" in debug:
        _open = lambda self: None
        _send = lambda self, s: sys.stderr.write("DBG: > %s" % (repr(s)))
        _recv = lambda self, len: input("DBG: < #%s:" % (len))[:len]
        _close = lambda self: None

    if "io" in debug:
        _open = _dbg(_open)
        _recv = _dbg(_recv)
        _send = _dbg(_send)
        _close = _dbg(_close)

    _headfmt = "!H H"

    def _read_frags(self, many=False):
        while True:
            header = self._recv(calcsize(self._headfmt))
            flags, num = unpack(self._headfmt, header)
            if not many or not flags:
                yield self._recv(num)
            else:
                break
            if not many:
                break

    def _read(self, many=False):
        rx = b"".join(self._read_frags(many))
        return rx

    def _write(self, string):
        return self._send(string)

    _respfmt = "!H H 4x L"

    def _sresp(self):
        ret = self._read()
        self.sta, self.err, self.cnt = unpack(
            self._respfmt, ret[: calcsize(self._respfmt)]
        )
        return ret[calcsize(self._respfmt) :]

    def _scmd(self, id, argsfmt=b"", *args):
        # assert calcsize("!B" + argsfmt) == 12
        # pad to 12 bytes
        argsfmt += b"%dx" % (12 - calcsize(b"!B" + argsfmt))
        self._write(pack(b"!B" + argsfmt, *((id,) + args)))
        return self._sresp()

    def ibdev(self, pad, sad=0, tmo=13, eot=1, eos=0):
        # first check if device is enet1000
        enet_5000 = EnetSocket(self._host, 5000)
        intro_resp = enet_5000._scmd(0x0b)
        self.enet1000 = intro_resp.find(b"ENET/1000") > -1
        if self.enet1000:
            i, h = unpack("!IH", enet_5000._scmd(0x63, b"B", 0x06))
            client_id = enet_5000._scmd(0x64)
            enet_5000._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)
            enet_5000._scmd(0x50, b"B", 0x05)
            enet_5000._scmd(0x50, b"B", 0x25)
            enet_5000._scmd(0x07, b"BBBBBBBB", 0, 0x18, 0x01, 0, 0, 0, 0, 0x0d)
            enet_5000._scmd(0x50, b"BB", 0x10, 0x01)

            enet_5015 = EnetSocket(self._host, 5015)
            self._extra_socket.append(enet_5015)
            enet_5015._scmd(0x55, b"B4sHI", 0x02, b"\0\0\0\0", h, i)
            enet_5015._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)

            enet_5003 = EnetSocket(self._host, 5003)
            self._extra_socket.append(enet_5003)
            enet_5003._scmd(0x63, b"B", 0x06)
            enet_5003._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)

            enet_5005 = EnetSocket(self._host, 5005)
            self._extra_socket.append(enet_5005)
            enet_5005._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)
            enet_5005._scmd(0x4f, b"B2sIH", 0x22, b"\0\0", i, h)

            enet_5003._scmd(0x50, b"BB", 0x10, 0x01)
            enet_5003._scmd(0x55, b"B4sHI", 0x01, b"\0\0\0\0", h, i)

            self._sock.connect()
            self._extra_socket.append(enet_5000)
            i, h = unpack(b"!IH", self._scmd(0x63, b"B", 0x06))
            self._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)

            self._scmd(
                0x07, b"BBBBBBBBBB", 0x02, 0, eot, pad, sad, eos, 0, tmo, 0, 0x04
            )
            self._scmd(0x50, b"B", 0x05)
            self._scmd(0x50, b"BB", 0x10, 0x01)
            self._scmd(0x50, b"BB", 0x15, 0x0b)

            enet_5015 = EnetSocket(self._host, 5015)
            self._extra_socket.append(enet_5015)
            enet_5015._scmd(0x55, b"BBBBBHI", 0x02, 0, 0x02, 0, 0, h, i)
            enet_5015._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)

            enet_5003 = EnetSocket(self._host, 5003)
            self._extra_socket.append(enet_5003)
            enet_5003._scmd(0x63, b"B", 0x06)
            enet_5003._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)

            enet_5005 = EnetSocket(self._host, 5005)
            self._extra_socket.append(enet_5005)
            enet_5005._scmd(0x65, b"BBB4s", 0, 0, 0, client_id)
            enet_5005._scmd(0x4f, b"B2sIH", 0x22, b"\0\0", i, h)

            enet_5003._scmd(0x55, b"BBBBBHI", 0x01, 0, 0x02, 0, 0, h, i)
            enet_5003._scmd(0x50, b"BB", 0x10, 0x01)

            self._scmd(0x58, b"BB", 0x01, 0x01)
        else:
            self._extra_socket.append(enet_5000)
            first_msg = intro_resp.find(b"\0")
            client_id = intro_resp[first_msg + 10 : first_msg + 10 + 6]
            i, h = unpack(b"!IH", client_id)
            enet_5000._scmd(0x50, b"B", 0x05)
            enet_5000._scmd(0x07, b"BBBBBBBB", 0, 0x18, 0x01, 0, 0, 0, 0, 0x0d)
            enet_5000._scmd(0x50, b"BB", 0x10, 0x01)

            enet_5015 = EnetSocket(self._host, 5015)
            self._extra_socket.append(enet_5015)
            enet_5015._scmd(0x55, b"B4sHI", 0x02, b"\0\0\0\0", h, i)

            self._sock.connect()
            self._scmd(
                0x07, b"BBBBBBBBBB", 0x02, 0, eot, pad, sad, eos, 0, tmo, 0, 0x04
            )
            self._scmd(0x50, b"B", 0x05)
            self._scmd(0x50, b"BB", 0x10, 0x01)
            self._scmd(0x50, b"BB", 0x15, 0x0b)

            enet_5015 = EnetSocket(self._host, 5015)
            self._extra_socket.append(enet_5015)
            enet_5015._scmd(0x55, b"BBBBBHI", 0x02, 0, 0x02, 0, 0, h, i)

            self._scmd(0x58, b"BB", 0x01, 0x01)

    def ibask(self, cfg):
        self._scmd(0x4e, b"B", cfg)
        #      "\x00\x00\x10\x00\x00\x00\x40\x63\x16\x40")
        return self.err

    def ibconfig(self, cfg, val):
        self._scmd(0x06, b"B B", cfg, val)

    #      "\x08\x00\x00\x00\x00\x00\x54\x00\x00")
    # return self.err # prevval

    def ibwait(self, mask=0):
        self._scmd(0x22, b"B H", 0x54, mask)

    #      "\x20\xe1\x05\x08\xb4\xe0\x05\x08")

    def ibrsp(self):
        stb, = unpack(b"!B", self._scmd(0x19))
        #      "\x63\x16\x40\xc0\x58\x16\x40\x40\x63\x16\x40"))
        return stb

    def ibonl(self, val=0):
        self._scmd(0x12, b"B", val)

    #      "\x00\x00\x20\xe1\x05\x08\xb3\xe0\x05\x08")

    def ibclr(self):
        self._scmd(0x04)

    #      "\xf5\xff\xbf\x14\xf5\xff\xbf\xa9\x8f\x04\x08")

    def ibeos(self, val):
        self._scmd(0x08, b"H", val)

    #      "\x00\x20\xe1\x05\x08\xb3\xe0\x05\x08")

    def ibeot(self, val):
        self._scmd(0x09, b"B", val)

    #      "\x00\x00\x20\xe1\x05\x08\xb3\xe0\x05\x08")

    def iblines(self):
        lines, = unpack("!H", self._scmd(0x0d))
        #      "\x63\x16\x40\xc0\x58\x16\x40\x40\x63\x16\x40"))
        return lines

    def ibln(self, pad, sad=0):
        if sad != 0:
            pad |= 0x80
        listen, = unpack(b"!H", self._scmd(0x0f, b"B B", pad, sad))
        #      "\x00\xf0\x38\x06\x08\x03\x00\x00\x00"))
        return listen

    def ibloc(self):
        self._scmd(0x10)

    #      "\xf5\xff\xbf\x14\xf5\xff\xbf\xa9\x8f\x04\x08")

    def ibtmo(self, tmo):
        self._scmd(0x1f, b"B", tmo)

    #      "\x00\x00\x20\xe1\x05\x08\xae\xe0\x05\x08")

    def ibtrg(self):
        self._scmd(0x20)

    #      "\xf5\xff\xbf\x14\xf5\xff\xbf\xa9\x8f\x04\x08")

    def ibcac(self, val=1):
        self._scmd(0x03, b"B", val)

    #      "\x00\x00\x20\xe1\x05\x08\xb1\xe0\x05\x08")

    def ibgts(self, val=1):
        self._scmd(0x0a, b"B", val)

    #      "\x00\x00\x20\xe1\x05\x08\xb1\xe0\x05\x08")

    def ibrsc(self, val=1):
        self._scmd(0x18, b"B", val)

    #      "\x00\x00\x20\xe1\x05\x08\xb1\xe0\x05\x08")

    def ibsic(self):
        self._scmd(0x1c)

    #      "\xe1\x05\x08\xb1\xe0\x05\x08\x88\xf5\xff\xbf")

    def ibwrt(self, string):
        argsfmt = b"3s I"
        argsfmt += b"%dx" % (12 - calcsize(b"!B" + argsfmt))
        header = pack(b"!B" + argsfmt, 0x62, b"\0\0\0", len(string))
        self._write(header + string)
        self._sresp()
        if self.err:
            raise IOError("No device connected to this address")
        return self.cnt

    def ibrd(self, num):
        argsfmt = b"3s I"
        argsfmt += b"%dx" % (12 - calcsize(b"!B" + argsfmt))
        self._write(pack(b"!B" + argsfmt, 0x16, b"\0\0\0", num))
        if not self.enet1000:
            self._sresp()

        ret = self._read(many=True)
        self._sresp()
        return ret

    if "rw" in debug:
        ibwrt = _dbg(ibwrt)
        ibrd = _dbg(ibrd)

    ibbna = _not_impl("ibbna")
    ibcmd = _not_impl("ibcmd")
    ibcmda = _not_impl("ibcmda")
    ibwrta = _not_impl("ibwrta")
    ibdiag = _not_impl("ibdiag")
    ibdma = _not_impl("ibdma")
    ibevent = _not_impl("ibevent")
    ibfind = _not_impl("ibfind")
    ibist = _not_impl("ibist")
    ibllo = _not_impl("ibllo")
    ibpad = _not_impl("ibpad")
    ibpct = _not_impl("ibpct")
    ibpoke = _not_impl("ibpoke")
    ibppc = _not_impl("ibppc")
    ibrda = _not_impl("ibrda")
    ibrdf = _not_impl("ibrdf")
    ibrdkey = _not_impl("ibrdkey")
    ibrpp = _not_impl("ibrpp")
    ibrsv = _not_impl("ibrsv")
    ibsad = _not_impl("ibsad")
    ibsgnl = _not_impl("ibsgnl")
    ibsre = _not_impl("ibsre")
    ibsrq = _not_impl("ibsrq")
    ibstop = _not_impl("ibstop")
    ibwrta = _not_impl("ibwrta")
    ibwrtf = _not_impl("ibwrtf")
    ibwrtkey = _not_impl("ibwrtkey")
    ibxtrc = _not_impl("ibxtrc")


class EnetLib(object):
    def __init__(self, host, port=5000):
        self._host = host
        self._port = port
        self._uds = {0: None}

    def _wrap_ud(self, name):
        def wrapped(ud, *a, **ka):
            res = getattr(self._uds[ud], name)(*a, **ka)
            if res == None:
                return self._uds[ud].sta
            else:
                return self._uds[ud].sta, res

        return wrapped

    # TODO: cfg
    def ibfind(self, name):
        if name[:3] == "dev":
            pad = int(name[3:])
        else:
            raise ValueError("configuration not yet implemented. use devX")
        return self.ibdev(pad)

    def ibdev(self, *a, **ka):
        ud = max(self._uds.keys()) + 1
        self._uds[ud] = EnetSocket(self._host, self._port)
        self._uds[ud].ibdev(*a, **ka)
        return ud

    def ibonl(self, ud, val):
        self._uds[ud].ibonl(val)
        sta = self._uds[ud].sta
        if not val:
            del self._uds[ud]
        return sta

    def ibsta(self):
        return 0

    def iberr(self):
        return 0

    def ibcntl(self):
        return 0

    ibcnt = ibcntl

    def __getattr__(self, name):
        return self._wrap_ud(name)


if __name__ == "__main__":
    nienet_host = "qo-hpf-gpib1.ethz.ch"
    l = EnetLib(nienet_host)
    ud = l.ibdev(pad=13)
    print("ibrsp", l.ibrsp(ud))
    print("iblines", l.iblines(ud))
    print("ibtrg", l.ibtrg(ud))
    print("ibask", l.ibask(ud, 1))
    print("ibln 13", l.ibln(ud, 13))
    print("ibln 11", l.ibln(ud, 11))
    print("ibwrt", l.ibwrt(ud, "ID?;"))
    print("ibrd", l.ibrd(ud, 10))
    print("ibwrt", l.ibwrt(ud, "SET?;"))
    print("ibrd", repr(l.ibrd(ud, 640)))
    print("ibwrt", l.ibwrt(ud, "DSTB;"))
    print("ibrd", repr(l.ibrd(ud, 4096)))
    print("ibbna", l.ibbna(ud))
