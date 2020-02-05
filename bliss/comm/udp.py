# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""UDP communication module (:class:`~bliss.comm.udp.Udp`, \
:class:`~bliss.comm.udp.Socket`)
"""

import re
from gevent import socket
from .tcp import BaseSocket
from .util import HexMsg
from bliss.common.logtools import *


class Socket(BaseSocket):
    def __info__(self):
        info_str = "UDP SOCKET:  host={self._host} port={self._port} \n"
        return info_str

    def _connect(self, host, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_IP, socket.IP_TOS, 0x10)
        sock.connect((host, port))
        return sock

    def _sendall(self, data):
        log_debug_data(self, "Tx:", data)
        return self._socket.send(data)

    @staticmethod
    def _raw_read(bliss_socket, sock):
        try:
            while 1:
                raw_data = sock.recv(16 * 1024)
                log_debug_data(bliss_socket, "Rx:", raw_data)
                if raw_data:
                    bliss_socket._data += raw_data
                    bliss_socket._event.set()
                else:
                    break
        except:
            pass
        finally:
            sock.close()
            try:
                bliss_socket._connected = False
                bliss_socket._socket = None
                bliss_socket._event.set()
            except ReferenceError:
                pass


class Udp:
    def __new__(cls, url=None, **keys):
        # for now only one udp class
        # no need to test...
        parse = re.compile(r"^(socket://)?([^:/]+?):([0-9]+)$")
        match = parse.match(url)
        if match is None:
            raise UdpError("Socket: url is not valid (%s)" % url)
        host, port = match.group(2), int(match.group(3))
        return Socket(host, port, **keys)
