# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""UDP communication module (:class:`~bliss.comm.udp.Udp`, \
:class:`~bliss.comm.udp.Socket`)
"""

import re
from gevent import socket
from .tcp import BaseSocket
from .util import HexMsg


class Socket(BaseSocket):
    def _connect(self, host, port):
        fd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        fd.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        fd.connect((host, port))
        return fd

    def _sendall(self, data):
        self._debug("Tx: %r %r", data, HexMsg(data))
        return self._fd.send(data)

    @staticmethod
    def _raw_read(sock, fd):
        try:
            while 1:
                raw_data = fd.recv(16 * 1024)
                sock._debug("Rx: %r %r", raw_data, HexMsg(raw_data))
                if raw_data:
                    sock._data += raw_data
                    sock._event.set()
                else:
                    break
        except:
            pass
        finally:
            fd.close()
            try:
                sock._connected = False
                sock._fd = None
                sock._event.set()
            except ReferenceError:
                pass


class Udp(object):
    def __new__(cls, url=None, **keys):
        # for now only one udp class
        # no need to test...
        parse = re.compile(r"^(socket://)?([^:/]+?):([0-9]+)$")
        match = parse.match(url)
        if match is None:
            raise UdpError("Socket: url is not valid (%s)" % url)
        host, port = match.group(2), int(match.group(3))
        return Socket(host, port, **keys)
