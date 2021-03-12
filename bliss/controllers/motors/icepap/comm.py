# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import socket
import time
import gevent
import hashlib
import functools
from collections import namedtuple
from bliss.common.greenlet_utils import protect_from_kill
from bliss.comm.tcp import Command
from bliss.comm.exceptions import CommunicationError
import struct
import numpy
import sys
import os
import errno

__all__ = ["_check_reply", "_vdata_header", "_command", "_command_raw", "_ackcommand"]

_check_reply = re.compile(r"^[#?]|^[0-9]+:\?")


def _vdata_header(data, axis, vdata_type, addr=None):
    PARDATA_HEADER_FORMAT = "<HBBLLBBHd"
    numpydtype_2_dtype = {
        numpy.dtype(numpy.int8): 0x00,
        numpy.dtype(numpy.int16): 0x01,
        numpy.dtype(numpy.int32): 0x02,
        numpy.dtype(numpy.int64): 0x03,
        numpy.dtype(numpy.float32): 0x04,
        numpy.dtype(numpy.float64): 0x05,
        numpy.dtype(numpy.uint8): 0x10,
        numpy.dtype(numpy.uint16): 0x11,
        numpy.dtype(numpy.uint32): 0x12,
        numpy.dtype(numpy.uint64): 0x13,
    }
    if not data.size:
        raise RuntimeError("Nothing to send")
    elif len(data) > 0xFFFF:
        raise ValueError("too many data values, max: 0xFFFF")

    dtype = numpydtype_2_dtype[data.dtype]
    data_test = data.newbyteorder("<")
    if data_test[0] != data[0]:  # not good endianness
        data = data.byteswap()

    header_size = struct.calcsize(PARDATA_HEADER_FORMAT)
    full_size = header_size + len(data.tostring())
    aligned_full_size = (full_size + 3) & ~3  # alignment 32 bits
    if addr is None:
        flags = vdata_type | axis.address
    else:
        flags = vdata_type | 255

    bin_header = struct.pack(
        PARDATA_HEADER_FORMAT,
        0xCAFE,  # vdata signature
        0,  # Version = 0
        header_size // 4,  # Data offset in dwords
        aligned_full_size // 4,  # Full vector size in dwords
        len(data),  # number of values in the vector
        dtype,  # Data type
        0,  # no compression
        flags,  # format + address
        0,
    )  # first data value for incremental coding
    return numpy.fromstring(
        bin_header + data.tostring() + b"\0" * (aligned_full_size - full_size),
        dtype=numpy.int8,
    )


@protect_from_kill
def _command(cnx, cmd, data=None, pre_cmd=None, timeout=None):
    try:
        return _command_raw(cnx, cmd, data, pre_cmd, timeout=timeout)

    except socket.gaierror as sockexc:
        _msg = f"socket.gaierror no {sockexc.errno} : {sockexc.strerror}"
        raise CommunicationError(_msg) from sockexc

    except IOError as ioex:
        if ioex.errno == 113:
            _msg = f"IOError no {ioex.errno}:{errno.errorcode[ioex.errno]}"
            _msg += f"\nmessage={os.strerror(ioex.errno)} "
            _msg += f"\nPlease check that icepap controller '{cnx._host}' is ON"
        else:
            _msg = f"IOError no {ioex.errno} : {ioex.strerror}"
            _msg += f"\nCannot communicate with icepap controller: '{cnx._host}'"

        raise CommunicationError(_msg) from ioex


def _command_raw(cnx, cmd, data=None, pre_cmd=None, timeout=None):
    reply_flag = _check_reply.match(cmd)
    cmd = cmd.encode()
    if data is not None:
        uint16_view = data.view(dtype=numpy.uint16)
        data_checksum = uint16_view.sum()
        header = struct.pack(
            "<III",
            0xA5AA555A,  # Header key
            len(uint16_view),
            int(data_checksum) & 0xFFFFFFFF,
        )

        data_test = data.newbyteorder("<")
        if len(data_test) and data_test[0] != data[0]:  # not good endianness
            data = data.byteswap()

        full_cmd = b"%s\n%s%s" % (cmd, header, data.tostring())
        transaction = cnx._write(full_cmd)
    else:
        if pre_cmd:
            full_cmd = b"%s%s\n" % (pre_cmd.encode(), cmd)
        else:
            full_cmd = b"%s\n" % cmd
        transaction = cnx._write(full_cmd)
    with cnx.Transaction(cnx, transaction):
        if reply_flag:
            msg = cnx._readline(
                transaction=transaction, clear_transaction=False, timeout=timeout
            )
            cmd = cmd.strip(b"#").split(b" ")[0]
            msg = msg.replace(cmd + b" ", b"")
            if msg.startswith(b"$"):
                msg = cnx._readline(
                    transaction=transaction,
                    clear_transaction=False,
                    eol=b"$\n",
                    timeout=timeout,
                )
            elif msg.startswith(b"ERROR"):
                raise RuntimeError(msg.replace(b"ERROR ", b"").decode())
            elif msg.startswith(b"?*"):
                # a binary reply
                header = cnx._read(transaction, size=12, clear_transaction=False)
                dfmt, magic, size, checksum = struct.unpack("<HHII", header)
                assert magic == 0xA5A5
                dsize = dfmt & 0xF  # data size (bytes)
                data = cnx._read(
                    transaction, size=dsize * size, clear_transaction=False
                )
                return numpy.fromstring(data, dtype="u{0}".format(dsize))
            return msg.strip(b" ").decode()


def _ackcommand(cnx, cmd, data=None, pre_cmd=None):
    if not cmd.startswith("#") and not cmd.startswith("?"):
        cmd = "#" + cmd
    return _command(cnx, cmd, data, pre_cmd)
