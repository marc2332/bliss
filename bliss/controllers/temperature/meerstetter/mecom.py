# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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

# Different debug levels are:
# log.NOTSET = 0, log.DEBUG = 10, log.INFO = 20, log.ERROR=40
import logging


def set_mecom_log_level(level):
    level = level.upper()
    logging.getLogger("MeComProtocol").setLevel(level)
    logging.getLogger("TECFamilyProtocol").setLevel(level)


# set_mecom_log_level('debug')


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
        self.log = logging.getLogger("MeComProtocol")
        self.log.info("__init__: %s %d" % (sock_comm, dev_addr))

    def PutGet(self, cmd, anslen, eof):
        # self.log.info("PutGet: %s, %d, %c" %(cmd,anslen,eof))
        self.log.info("PutGet: %s, %d, %r" % (cmd, anslen, eof))

        frame = self.FrameConstruction(cmd, eof)

        try:
            return self._PutGet(frame, cmd, anslen, eof)

        except AssertionError, e:
            self.log.error("PutGet: Device communication assertion error: %s" % (e))
        except tcp.SocketTimeout:
            self.log.error("PutGet: Socket communication timed out")
        except gevent.socket.error, e:
            self.log.error("PutGet: Socket communication error: %s" % (e))
        # except RunTimeError, e:
        #    log.error("MeComProtocol::PutGet: Runtime error: %s" %(e))

    def _PutGet(self, frame, cmd, anslen, eof):

        self.log.info("_PutGet: Frame  = %s" % frame)
        self.log.info("_PutGet: cmd    = %s" % cmd)
        self.log.info("_PutGet: anslen = %d" % anslen)
        self.log.info("_PutGet: eof    = %r" % eof)

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
            self._sock.readline(eol="\r\n\r\n")

        answer = self._sock.write_readline(frame, eol=eof)

        self.log.debug("_PutGet: Read buffer = %r " % answer)

        if answer == "":
            self.log.error("_PutGet: Socket connection broken")
            raise RuntimeError("MeComProtocol::_PutGet: Socket connection broken")

        resp = frame[:7].replace("#", "!")
        self.log.debug("_PutGet: 1st 7 char of frame with ! as 1st char: %s" % resp)
        if answer.startswith(resp):

            if answer[7] == "+":
                err = answer[8:10]
                self.log.debug("_PutGet:Error: %s", err)
                self.log.debug("_PutGet:Error: %d", int(err))
                self.log.debug("_PutGet:Error: %s", _error[int(err)])

            else:
                if cmd[0] == "?":  # query commands
                    self.log.debug("_PutGet: It is a query command")

                    assert len(answer) == (11 + anslen), "answer length not expected."
                    answ = answer[7 : anslen + 7]
                    blacrc = self._CRC16Algorithm(resp + answ)
                    self.log.debug("_PutGet: %s", answ)
                    return answ

                else:  # set commands
                    self.log.debug("_PutGet: ACK")
                    return "ACK"

        self.log.debug("_PutGet: NAK")
        return "NAK"

    def FrameConstruction(self, payload, eof):
        self.log.info("FrameConstruction: %s, %r" % (payload, eof))

        frame = []

        try:
            frame.extend("%02x" % (self.dev_addr))
            frame.extend("%04x" % (self._AssignSequenceNumber()))
            frame.extend(payload)
            frame.insert(0, "#")

            self.CRC = self._CRC16Algorithm(frame)

            if self.CRC > 0xffff:
                self.log.error(
                    "FrameConstruction: too large numeric CRC: %x" % (self.CRC)
                )
                raise RuntimeError, "too large numeric CRC: %x." % (self.CRC)

            frame.extend("%04x%s" % (self.CRC, eof))

        except RuntimeError, e:
            self.log.error("FrameConstruction ERROR %s" % (e))

        finally:
            pass

        # self.log.debug("FrameConstruction %s" %(frame))
        self.log.debug("FrameConstruction %r" % (frame))
        return "".join(frame).upper()

    def _CRC16Algorithm(self, frame):
        self.log.info("_CRC16Algorithm %s" % (frame))

        crc = 0
        genpoly = 0x1021

        for c in frame:
            c = ord(c.upper())
            c2 = (c & 0x00ff) << 8
            crc = crc ^ c2
            for i in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ genpoly
                else:
                    crc = crc << 1
            crc &= 0xffff

        self.log.debug("_CRC16Algorithm %04x" % (crc))
        return crc

    def _AssignSequenceNumber(self):

        if self.sequence < 65534:
            self.sequence += 1
        else:
            self.sequence = 0

        self.log.debug("_AssignSequenceNumber %d" % (self.sequence))
        return self.sequence


######################################################################
############################              ############################
############################  TEC Family  ############################
############################              ############################
######################################################################


class TECFamilyProtocol(object):
    def __init__(self, sock_comm, dev_addr):

        self.mecom = MeComProtocol(sock_comm, dev_addr)
        self.log = logging.getLogger("TECFamilyProtocol")
        self.log.info("__init__: %s %d" % (sock_comm, dev_addr))

    def putget(self, command, anslen=0, EOF="\r"):
        self.log.info("putget")
        self.log.debug("putget: cmd = %s, anslen = %d " % (command, anslen))

        ret = self.mecom.PutGet(command, anslen, EOF)

        return ret

    # getModel = get Firmware Identification String
    def getModel(self):
        self.log.info("getModel")

        self.model = self.putget("?IF", 20)

        self.log.debug("getModel: %s" % (self.model))
        return self.model

    def _getParameter(self, id, anslen, instance=1):
        self.log.debug("_getParameter %04x %d %02x" % (id, anslen, instance))

        if id > 0xffff:
            raise RuntimeError, "wrong parameter id: %x." % (id)

        if instance > 0xff:
            raise RuntimeError, "wrong parameter instance: %x." % (instance)

        payload = ["?", "V", "R"]
        payload.extend("%04x" % (id))
        payload.extend("%02x" % (instance))
        self.log.debug("_getParameter payload %r" % payload)

        answer = self.putget("".join(payload), anslen)

        self.log.debug("_getParameter: %s" % (answer))
        return answer

    def _setParameter(self, id, parameter, instance=1):
        self.log.info("_setParameter %04x %04x %02x" % (id, parameter, instance))

        if id > 0xffff:
            raise RuntimeError, "wrong parameter id: %x." % (id)

        if instance > 0xff:
            raise RuntimeError, "wrong parameter instance: %x." % (instance)

        payload = ["V", "S"]
        payload.extend("%04x" % (id))
        payload.extend("%02x" % (instance))

        parameter = struct.pack(">f", parameter).encode("hex")
        payload.extend("%s" % (parameter))

        answer = self.putget(payload)

        self.log.debug("_getParameter %s" % (answer))
        return answer
