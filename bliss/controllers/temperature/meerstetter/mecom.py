# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Meerstetter communication protocol related 

    The code for classes MeComProtocol and TECFamilyProtocol
    is based on the code found in the file 
    ting:~blissadm/server/src/Temperature/LTR1200.py,
    which was created to be used by LTR1200TemperatureDS
    Tango DS. 
    In the class TECFamilyProtocol only "base" functions were
    retained and the functions for setting/getting different
    features are rather implemented in the "low-level" class
    Ltr1200 in the file ltr1200.py.

"""

from bliss.comm import tcp
import gevent

import struct

import time

######################################################################
###########################                ###########################
########################### MeCOM PROTOCOL ###########################
###########################                ###########################
######################################################################
#
# Frame Fields:
# ------------
#     8 bits: control source field ("!" for input, "#" for output)
#    16 bits: device address
#    32 bits: random sequence identifier
# N * 8 bits: client command (so called payload)
#    32 bits: frane CRC checksum
#     8 bits: frame terminator \r (eof = end of frame)
#
######################################################################


class MeComProtocol(object):
    def __init__(self, sock_comm, dev_addr):
        self.sequence = 0
        self._sock = sock_comm
        self.dev_addr = dev_addr

    def PutGet(self, cmd, anslen, eof):
        frame = self.FrameConstruction(cmd, eof)
        return self._PutGet(frame, cmd, anslen, eof)

    def _PutGet(self, frame, cmd, anslen, eof):
        _error = [
            "Unknown error",
            "Command not available",
            "Device is busy",
            "General communication error",
            "Format error",
            "Parameter is not available",
            "Parameter is read only",
            "Value out of range",
            "Instance not available",
        ]
        if not self._sock._connected:
            self._sock.connect()
            self._sock.readline(eol=b"\r\n\r\n")

        answer = self._sock.write_readline(frame.encode(), eol=eof.encode())

        if answer == "":
            raise RuntimeError("MeComProtocol::_PutGet: Socket connection broken")

        resp = (frame[:7].replace("#", "!")).encode()
        if answer.startswith(resp):

            if answer[7] == "+":
                err = answer[8:10]
            else:
                if cmd[0] == "?":  # query commands
                    assert len(answer) == (11 + anslen), "answer length not expected."
                    answ = answer[7 : anslen + 7]
                    blacrc = self._CRC16Algorithm(resp + answ)
                    return answ
                else:  # set commands
                    return "ACK"

        return "NAK"

    def FrameConstruction(self, payload, eof):
        frame = []

        frame.extend("%02x" % (self.dev_addr))
        frame.extend("%04x" % (self._AssignSequenceNumber()))
        frame.extend(payload)
        frame.insert(0, "#")

        frame = "".join(frame)
        self.CRC = self._CRC16Algorithm(frame.encode())

        if self.CRC > 0xFFFF:
            raise RuntimeError("too large numeric CRC: %x." % (self.CRC))

        frame = frame + ("%04x%s" % (self.CRC, eof))

        return "".join(frame).upper()

    def _CRC16Algorithm(self, frame):
        frame = frame.upper()
        crc = 0
        genpoly = 0x1021

        for c in frame:
            c2 = (c & 0x00FF) << 8
            crc = crc ^ c2
            for i in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ genpoly
                else:
                    crc = crc << 1
            crc &= 0xFFFF

        return crc

    def _AssignSequenceNumber(self):

        if self.sequence < 65534:
            self.sequence += 1
        else:
            self.sequence = 0

        return self.sequence


######################################################################
############################              ############################
############################  TEC Family  ############################
############################              ############################
######################################################################


class TECFamilyProtocol(object):
    def __init__(self, sock_comm, dev_addr):

        self.mecom = MeComProtocol(sock_comm, dev_addr)

    def putget(self, command, anslen=0, EOF="\r"):
        ret = self.mecom.PutGet(command, anslen, EOF)

        return ret

    # getModel = get Firmware Identification String
    def getModel(self):
        self.model = self.putget("?IF", 20)
        return self.model

    def _getParameter(self, id, anslen, instance=1):
        if id > 0xFFFF:
            raise RuntimeError("wrong parameter id: %x." % (id))

        if instance > 0xFF:
            raise RuntimeError("wrong parameter instance: %x." % (instance))

        payload = ["?", "V", "R"]
        payload.extend("%04x" % (id))
        payload.extend("%02x" % (instance))

        answer = self.putget("".join(payload), anslen)

        return answer

    def _setParameter(self, id, parameter, instance=1):
        if id > 0xFFFF:
            raise RuntimeError("wrong parameter id: %x." % (id))

        if instance > 0xFF:
            raise RuntimeError("wrong parameter instance: %x." % (instance))

        payload = ["V", "S"]
        payload.extend("%04x" % (id))
        payload.extend("%02x" % (instance))

        parameter = struct.pack(">f", parameter).encode("hex")
        payload.extend("%s" % (parameter))

        answer = self.putget(payload)

        return answer
