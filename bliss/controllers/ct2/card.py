# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
The python module for the ct2 (P201/C208) ESRF PCI counter card
"""


import os
import sys
import stat
import time
import errno
import fcntl
import ctypes
import ctypes.util
import select
import struct
import logging
import weakref
import functools
import string

import enum

import numpy


# low level pread and pwrite calls for the p201/c208 driver.

# even if we are using python >=  3.3 we cannot use os.pread/pwrite calls
# because of the semantics of the p201/c208 driver. For example, the read
# returns the number of adjacent registers that we actually read instead
# of the the number of bytes read like the linux programmer's manual specifies

__libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
__librt = ctypes.CDLL(ctypes.util.find_library("rt"), use_errno=True)


ct2_size_type = ctypes.c_size_t
ct2_reg_t = ctypes.c_uint32
ct2_reg_dist_t = ctypes.c_uint8

CT2_SIZE = ctypes.sizeof(ct2_size_type)

#:
#: ct2 register size (bytes)
#:
CT2_REG_SIZE = ctypes.sizeof(ct2_reg_t)


class timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]


class ct2_in(ctypes.Structure):
    _fields_ = [("ctrl_it", ct2_reg_t), ("stamp", timespec)]


class ct2_inv(ctypes.Structure):
    _fields_ = [("inv", ctypes.POINTER(ct2_in)), ("inv_len", ct2_size_type)]


CT2_IN_SIZE = ctypes.sizeof(ct2_in)


# for python < 3.3 define clock_gettime
clock_gettime = getattr(time, "clock_gettime", None)
if not hasattr(time, "clock_gettime"):
    # see <linux/time.h>
    time.CLOCK_REALTIME = 0
    time.CLOCK_MONOTONIC = 1
    time.CLOCK_PROCESS_CPUTIME_ID = 2
    time.CLOCK_THREAD_CPUTIME_ID = 3
    time.CLOCK_MONOTONIC_RAW = 4

    __clock_gettime = __librt.clock_gettime
    __clock_gettime.argtypes = [ctypes.c_int, ctypes.POINTER(timespec)]

    def _clock_gettime(clk_id):
        t = timespec()
        if __clock_gettime(clk_id, ctypes.pointer(t)) != 0:
            errno_ = ctypes.get_errno()
            errno.set_errno(0)
            raise OSError(errno_, "time.monotonic error: %s" % os.strerror(errno_))
        return t.tv_sec + t.tv_nsec * 1E-9

    time.clock_gettime = _clock_gettime
    time.monotonic = functools.partial(time.clock_gettime, time.CLOCK_MONOTONIC_RAW)
time.monotonic_raw = functools.partial(time.clock_gettime, time.CLOCK_MONOTONIC_RAW)


def pread(fd, offset, n=CT2_REG_SIZE):
    """
    :param fd: fileno
    :type fd: int
    :param offset: offset (in bytes)
    :type offset: int
    :param n: number of bytes to read starting at offset
    """
    buff = ctypes.create_string_buffer(n)
    read_n = __libc.pread(fd, buff, n, offset)
    if read_n == -1:
        err = ctypes.get_errno()
        if err != 0:
            ctypes.set_errno(0)
            raise OSError(
                "pread error: %s (%d): %s"
                % (errno.errorcode[err], err, os.strerror(err))
            )
        else:
            raise OSError("pread error")
    elif read_n != n:
        raise OSError(
            "pread error: read only {0} bytes (expected {1})".format(read_n, n)
        )
    return buff[:]


def pwrite(fd, buff, offset):
    length = len(buff)
    write_n = __libc.pwrite(fd, buff, length, offset)
    if write_n == -1:
        err = ctypes.get_errno()
        if err != 0:
            ctypes.set_errno(0)
            raise OSError(
                "pwrite error: %s (%d): %s"
                % (errno.errorcode[err], err, os.strerror(err))
            )
        else:
            raise OSError("pwrite error")
    elif write_n != length:
        raise OSError(
            "pwrite error: wrote only {0} bytes (expected {1})".format(write_n, length)
        )
    return write_n


class BaseCardInterface(object):
    def connect(self):
        pass

    def disconnect(self):
        pass

    def pread(self, offset, n=CT2_REG_SIZE):
        raise NotImplementedError

    def pwrite(self, buff, offset):
        raise NotImplementedError

    def ioctl(self, op, *args, **kwargs):
        raise NotImplementedError

    def read_offset(self, offset):
        result = self.pread(offset)
        iresult = struct.unpack("I", result)[0]
        return iresult

    def read_offset_array(self, offset, nb_reg=1):
        result = self.pread(offset, n=CT2_REG_SIZE * nb_reg)
        return numpy.frombuffer(result, dtype=numpy.uint32)

    def write_offset(self, offset, ivalue):
        svalue = struct.pack("I", int(ivalue))
        return self.pwrite(svalue, offset)

    def write_offset_array(self, offset, array):
        return self.pwrite(array.tostring(), offset)


class CardInterface(BaseCardInterface):
    """
    Standard card interface
    """

    def __init__(self, address="/dev/ct2_0"):
        self.address = address
        self.__log = logging.getLogger(str(self))
        self.__dev = None

    def connect(self):
        self.disconnect()
        self.__log.info("connecting to %s", self.address)
        self.__dev = open(self.address, "rwb+", 0)

    def disconnect(self):
        if self.__dev:
            self.__log.info("disconnecting from %s", self.address)
            self.__dev.close()
        self.__dev = None

    def fileno(self):
        """
        internal card file descriptor (don't use this member directly on your
        code)
        """
        if self.__dev is None:
            raise CT2Exception("Card not connected to device")
        return self.__dev.fileno()

    def ioctl(self, op, *args, **kwargs):
        try:
            fcntl.ioctl(self.fileno(), op[0], *args, **kwargs)
            self.__log.debug("ioctl %020s", op[1])
        except (IOError, OSError) as exc:
            if exc.errno in op[2]:
                raise CT2Exception("{0} error: {1}".format(op[1], op[2][exc.errno]))
            else:
                raise

    def pread(self, offset, n=CT2_REG_SIZE):
        return pread(self.fileno(), offset, n=n)

    def pwrite(self, buff, offset):
        return pwrite(self.fileno(), buff, offset)

    def __str__(self):
        return "{0.__class__.__name__}({0.address})".format(self)

    def __repr__(self):
        return str(self)


class MemoryInterface(BaseCardInterface):
    """
    Emulate a card interface. You can use the result of
    method:`BaseCard.dump_memory()` as argument to construct
    this object and then create a card object. Example::

        from bliss.controllers.ct2 import P201Card, MemoryInterface

        real_card = P201Card()
        memory = real_card.dump_memory()

        memory_card = P201Card(MemoryInterface(memory))
        print(memory_card.get_counters_status())
    """

    def __init__(self, buff):
        self.buff = bytearray(buff)

    def pread(self, offset, n=CT2_REG_SIZE):
        return bytes(self.buff[offset : offset + n])

    def pwrite(self, buff, offset):
        self.buff[offset : offset + len(buff)] = buff

    def __str__(self):
        return "{0.__class__.__name__}()".format(self)

    def __repr__(self):
        return str(self)


# --------------------------------------------------------------------------
#                       Linux ioctl numbers made easy
# --------------------------------------------------------------------------

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8

# architecture specific
_IOC_SIZEBITS = 14
_IOC_DIRBITS = 2

_IOC_NRMASK = (1 << _IOC_NRBITS) - 1
_IOC_TYPEMASK = (1 << _IOC_TYPEBITS) - 1
_IOC_SIZEMASK = (1 << _IOC_SIZEBITS) - 1
_IOC_DIRMASK = (1 << _IOC_DIRBITS) - 1

_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS

_IOC_NONE = 0
_IOC_WRITE = 1
_IOC_READ = 2


def _IOC(dir, type, nr, size):
    if isinstance(size, str) or isinstance(size, str):
        size = struct.calcsize(size)
    return (
        dir << _IOC_DIRSHIFT
        | type << _IOC_TYPESHIFT
        | nr << _IOC_NRSHIFT
        | size << _IOC_SIZESHIFT
    )


def _IO(type, nr):
    return _IOC(_IOC_NONE, type, nr, 0)


def _IOR(type, nr, size):
    return _IOC(_IOC_READ, type, nr, size)


def _IOW(type, nr, size):
    return _IOC(_IOC_WRITE, type, nr, size)


def _IOWR(type, nr, size):
    return _IOC(_IOC_READ | _IOC_WRITE, type, nr, size)


# --------------------------------------------------------------------------
#                                Helpers
# --------------------------------------------------------------------------


def NOT(a):
    return 0xFFFFFFFF ^ a


@enum.unique
class Edge(enum.IntEnum):
    """Edge enumeration"""

    DISABLE = 0b00
    RISING = 0b01
    FALLING = 0b10
    RISING_FALLING = 0b11


@enum.unique
class Level(enum.IntEnum):
    """TTL/NIM level enumeration"""

    DISABLE = 0b00
    TTL = 0b01
    NIM = 0b10
    AUTO = 0b11


# ==========================================================================
#                           Register Definitions
# ==========================================================================


class CT2Exception(Exception):
    """
    ct2 exception class
    """

    pass


# R ... read with side effects
# W ... write with side effects
# r ... read without side effects (ie, with memory semantics)
# w ... write without side effects


# --------------------------------------------------------------------------
#                       PCI I/O Space 1 Registers Map
# --------------------------------------------------------------------------

CT2_R1_OFFSET = 0

CT2_R1_SEQ = [
    # addr        name      read  write             description
    [
        [0x00, "COM_GENE", True, True, "General control"],
        [0x04, "CTRL_GENE", True, False, "General status"],
    ],
    [
        [0x0C, "NIVEAU_OUT", True, True, "Output enable and type (TTL or NIM)"],
        [0x10, "ADAPT_50", True, True, "Input 50 ohms loads selector"],
        [0x14, "SOFT_OUT", True, True, "Output status control (when enabled)"],
        [0x18, "RD_IN_OUT", True, False, "Input and output readback"],
        [0x1C, "RD_CTRL_CMPT", True, False, "Counter ENABLE and RUN readback"],
        [
            0x20,
            "CMD_DMA",
            True,
            True,
            "DMA enable and trigger source, counters for storing selector",
        ],
        [0x24, "CTRL_FIFO_DMA", True, False, "FIFO status"],
        [0x28, "SOURCE_IT_A", True, True, "Interrupt source A selector"],
        [0x2C, "SOURCE_IT_B", True, True, "Interrupt source B selector"],
    ],
    [[0x30, "CTRL_IT", True, False, "Interrupt status and clear"]],
    [[0x34, "NIVEAU_IN", True, True, "Input level (TTL or NIM), selector"]],
    [
        [0x40, "RD_CMPT_1", True, False, "Counter 1 direct readout"],
        [0x44, "RD_CMPT_2", True, False, "Counter 2 direct readout"],
        [0x48, "RD_CMPT_3", True, False, "Counter 3 direct readout"],
        [0x4C, "RD_CMPT_4", True, False, "Counter 4 direct readout"],
        [0x50, "RD_CMPT_5", True, False, "Counter 5 direct readout"],
        [0x54, "RD_CMPT_6", True, False, "Counter 6 direct readout"],
        [0x58, "RD_CMPT_7", True, False, "Counter 7 direct readout"],
        [0x5C, "RD_CMPT_8", True, False, "Counter 8 direct readout"],
        [0x60, "RD_CMPT_9", True, False, "Counter 9 direct readout"],
        [0x64, "RD_CMPT_10", True, False, "Counter 10 direct readout"],
        [0x68, "RD_CMPT_11", True, False, "Counter 11 direct readout"],
        [0x6C, "RD_CMPT_12", True, False, "Counter 12 direct readout"],
    ],
    [
        [0x70, "RD_LATCH_CMPT_1", True, False, "Latch counter 1 readout"],
        [0x74, "RD_LATCH_CMPT_2", True, False, "Latch counter 2 readout"],
        [0x78, "RD_LATCH_CMPT_3", True, False, "Latch counter 3 readout"],
        [0x7C, "RD_LATCH_CMPT_4", True, False, "Latch counter 4 readout"],
        [0x80, "RD_LATCH_CMPT_5", True, False, "Latch counter 5 readout"],
        [0x84, "RD_LATCH_CMPT_6", True, False, "Latch counter 6 readout"],
        [0x88, "RD_LATCH_CMPT_7", True, False, "Latch counter 7 readout"],
        [0x8C, "RD_LATCH_CMPT_8", True, False, "Latch counter 8 readout"],
        [0x90, "RD_LATCH_CMPT_9", True, False, "Latch counter 9 readout"],
        [0x94, "RD_LATCH_CMPT_10", True, False, "Latch counter 10 readout"],
        [0x98, "RD_LATCH_CMPT_11", True, False, "Latch counter 11 readout"],
        [0x9C, "RD_LATCH_CMPT_12", True, False, "Latch counter 12 readout"],
    ],
    [[0xFC, "TEST_REG", True, True, "Test data register"]],
]

# make a dict, change the address: divide by register size + add the register map offset

CT2_R1_DICT = {}
for zone in CT2_R1_SEQ:
    for reg_info in zone:
        addr, name, r, w, desc = reg_info
        addr = CT2_R1_OFFSET + addr
        reg_info[0] = addr
        CT2_R1_DICT[name] = addr, r, w, desc
del reg_info, addr, name, r, w, desc, zone

# --------------------------------------------------------------------------
#                       PCI I/O Space 2 Registers Map
# --------------------------------------------------------------------------

CT2_R2_OFFSET = 64 * CT2_REG_SIZE

CT2_R2_SEQ = [
    # addr        name           read  write             description
    [
        [
            0x00,
            "SEL_FILTRE_INPUT_A",
            True,
            True,
            "Input 1 to 6: filter configuration and deglitcher enable",
        ],
        [
            0x04,
            "SEL_FILTRE_INPUT_B",
            True,
            True,
            "Input 7 to 10: filter configuration and deglitcher enable",
        ],
    ],
    [
        [
            0x10,
            "SEL_FILTRE_OUTPUT",
            True,
            True,
            "Output 9 and 10: filter configuration and polarity selection",
        ]
    ],
    [[0x1C, "SEL_SOURCE_OUTPUT", True, True, "Output 9 and 10: source selection"]],
    [
        [0x20, "SEL_LATCH_A", True, True, "Counter 1 and 2: latch source"],
        [0x24, "SEL_LATCH_B", True, True, "Counter 3 and 4: latch source"],
        [0x28, "SEL_LATCH_C", True, True, "Counter 5 and 6: latch source"],
        [0x2C, "SEL_LATCH_D", True, True, "Counter 7 and 8: latch source"],
        [0x30, "SEL_LATCH_E", True, True, "Counter 9 and 10: latch source"],
        [0x34, "SEL_LATCH_F", True, True, "Counter 11 and 12: latch source"],
    ],
    [
        [
            0x38,
            "CONF_CMPT_1",
            True,
            True,
            "Counter 1: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x3C,
            "CONF_CMPT_2",
            True,
            True,
            "Counter 2: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x40,
            "CONF_CMPT_3",
            True,
            True,
            "Counter 3: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x44,
            "CONF_CMPT_4",
            True,
            True,
            "Counter 4: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x48,
            "CONF_CMPT_5",
            True,
            True,
            "Counter 5: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x4C,
            "CONF_CMPT_6",
            True,
            True,
            "Counter 6: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x50,
            "CONF_CMPT_7",
            True,
            True,
            "Counter 7: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x54,
            "CONF_CMPT_8",
            True,
            True,
            "Counter 8: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x58,
            "CONF_CMPT_9",
            True,
            True,
            "Counter 9: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x5C,
            "CONF_CMPT_10",
            True,
            True,
            "Counter 10: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x60,
            "CONF_CMPT_11",
            True,
            True,
            "Counter 11: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
        [
            0x64,
            "CONF_CMPT_12",
            True,
            True,
            "Counter 12: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable",
        ],
    ],
    [
        [
            0x68,
            "SOFT_ENABLE_DISABLE",
            False,
            True,
            "Counters 1 to 12: software enable, disable",
        ],
        [
            0x6C,
            "SOFT_START_STOP",
            False,
            True,
            "Counters 1 to 12: software start, stop",
        ],
        [0x70, "SOFT_LATCH", False, True, "Counters 1 to 12: software latch"],
    ],
    [
        [0x74, "COMPARE_CMPT_1", True, True, "Counter 1 comparator value"],
        [0x78, "COMPARE_CMPT_2", True, True, "Counter 2 comparator value"],
        [0x7C, "COMPARE_CMPT_3", True, True, "Counter 3 comparator value"],
        [0x80, "COMPARE_CMPT_4", True, True, "Counter 4 comparator value"],
        [0x84, "COMPARE_CMPT_5", True, True, "Counter 5 comparator value"],
        [0x88, "COMPARE_CMPT_6", True, True, "Counter 6 comparator value"],
        [0x8C, "COMPARE_CMPT_7", True, True, "Counter 7 comparator value"],
        [0x90, "COMPARE_CMPT_8", True, True, "Counter 8 comparator value"],
        [0x94, "COMPARE_CMPT_9", True, True, "Counter 9 comparator value"],
        [0x98, "COMPARE_CMPT_10", True, True, "Counter 10 comparator value"],
        [0x9C, "COMPARE_CMPT_11", True, True, "Counter 11 comparator value"],
        [0xA0, "COMPARE_CMPT_12", True, True, "Counter 12 comparator value"],
    ],
]

# make a dict, change the address: divide by register size + add the register map offset

CT2_R2_DICT = {}
for zone in CT2_R2_SEQ:
    for reg_info in zone:
        addr, name, r, w, desc = reg_info
        addr = CT2_R2_OFFSET + addr
        reg_info[0] = addr
        CT2_R2_DICT[name] = addr, r, w, desc
del reg_info, addr, name, r, w, desc, zone

# --------------------------------------------------------------------------
#                       PCI I/O Registers Map
# --------------------------------------------------------------------------

CT2_R_SEQ = CT2_R1_SEQ + CT2_R2_SEQ
CT2_R_DICT = dict(CT2_R1_DICT)
CT2_R_DICT.update(CT2_R2_DICT)

# ============================================================================
#                  BIT FIELDS, MASKS, OFFSETS, MACROS DEFINITIONS
#
# N.B. Masks/offsets that are valid for both C208 and P201 start with CT2_,
#      C208 specific start with C208_, P201 specif.start with P201_
# ============================================================================

# ----------------------------------------------------------------------------
# Definitions for "low" 12 bits (0-11) and "high" 12 (16-27) bits masks
#             used to mask useful bits in several registers.
#             Since cards have 12 counters and on C208 also 12 channels, the
#             usefull register part is either "low" or "high" 12 bits.
#             For P201 which has only 10 channels, provide also masks for
#             "low" 10 bits (0-9) and "high" 12 (16-25) bits.
# ----------------------------------------------------------------------------
CT2_LO12BITS_MSK = 0x00000fff  # Mask for bits 0-11
CT2_LO12BITS_OFF = 0  # Offset for the low word
CT2_HI12BITS_MSK = 0x0fff0000  # Mask for bits 16-27
CT2_HI12BITS_OFF = 16  # Offset for the high word
CT2_LO10BITS_MSK = 0x000003ff  # Mask for bits 0-9
CT2_LO10BITS_OFF = 0  # Offset for the low word
CT2_HI10BITS_MSK = 0x03ff0000  # Mask for bits 16-25
CT2_HI10BITS_OFF = 16  # Offset for the high word


# --------------------------------------------------------------------------
#                         PCI I/O Space 1 Registers
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Definitions for the COM_GENE (general command) register(R/W)
# --------------------------------------------------------------------------
CT2_COM_GENE_UMSK = 0x0000009f  # Used bits mask
CT2_COM_GENE_ENAB_MSK = 0x00000010  # en(1)/dis(0)able oscillator
CT2_COM_GENE_SOFT_RESET = 0x00000080  # soft reset(1)
CT2_COM_GENE_FREQ_MSK = 0x0000000f  # Frequency bitmask
CT2_COM_GENE_FREQ_OFF = 0  # Frequency offset


@enum.unique
class Clock(enum.IntEnum):
    """
    Clock enumeration
    """

    CLK_DISABLE = 0b00000
    CLK_20_MHz = 0b10101
    CLK_25_MHz = 0b10100
    CLK_30_MHz = 0b10010
    CLK_33_33_MHz = 0b10001
    CLK_40_MHz = 0b11111
    CLK_45_MHz = 0b11101
    CLK_50_MHz = 0b11100
    CLK_60_MHz = 0b11010
    CLK_66_66_MHz = 0b11001
    CLK_70_MHz = 0b10110
    CLK_75_MHz = 0b11000
    CLK_80_MHz = 0b10111
    CLK_90_MHz = 0b11110
    CLK_100_MHz = 0b10000


# ----------------------------------------------------------------------------
# Definitions for the CTRL_GENE (general control) register(R)
# ----------------------------------------------------------------------------
C208_CTRL_GENE_UMSK = 0xfcffff7f  # Used bits mask
P201_CTRL_GENE_UMSK = 0x0000ff0f  # Used bits mask
CT2_CTRL_GENE_FIFO_MSK = 0x0000000f  # AMCC fifo flags mask
CT2_CTRL_GENE_FIFO_OFF = 0  # AMCC fifo flags offset
C208_CTRL_GENE_PLL_OK = 0x00000010  # external PLL synchronised
C208_CTRL_GENE_TEMP_ALERT = 0x00000020  # Virtex T > 126 degrees
C208_CTRL_GENE_TEMP_OVERT = 0x00000040  # Virtex T >  99 degrees
CT2_CTRL_GENE_CARDN_MSK = 0x0000ff00  # card(C208 or P201) ser.nb mask
CT2_CTRL_GENE_CARDN_OFF = 8  # card serial number offset
C208_CTRL_GENE_MEZZN_MSK = 0x00ff0000  # C208 mezzanine serial nb msk
C208_CTRL_GENE_MEZZN_OFF = 16  # C208 mezz. serial nb offset
C208_CTRL_GENE_3_3V_STA = 0x04000000  # status of 3.3V (1 = OK)
C208_CTRL_GENE_2_5V_STA = 0x08000000  # status of 2.5V (1 = OK)
C208_CTRL_GENE_1_8V_STA = 0x10000000  # status of 1.8V (1 = OK)
C208_CTRL_GENE_5V_STA = 0x20000000  # status of   5V (1 = OK)
C208_CTRL_GENE_P12V_STA = 0x40000000  # status of +12V (1 = OK)
C208_CTRL_GENE_M12V_STA = 0x80000000  # status of -12V (1 = OK)
C208_CTRL_GENE_LV_MSK = 0xfc000000  # LV status msk(all LVstogether)
C208_CTRL_GENE_LV_OFF = 26  # offset for LV status


def C208_VOLTS_OK(genctrl):
    return (
        (BIT_TST(genctrl, C208_CTRL_GENE_3_3V_STA))
        & (BIT_TST(genctrl, C208_CTRL_GENE_2_5V_STA))
        & (BIT_TST(genctrl, C208_CTRL_GENE_1_8V_STA))
        & (BIT_TST(genctrl, C208_CTRL_GENE_5V_STA))
        & (BIT_TST(genctrl, C208_CTRL_GENE_P12V_STA))
        & (BIT_TST(genctrl, C208_CTRL_GENE_M12V_STA))
    )


# ----------------------------------------------------------------------------
# Definitions for TEMPS (temperature) register(R) - only exists for C208
# ----------------------------------------------------------------------------
C208_TEMPS_VIRTEX_TEMP_MSK = 0x0000007f  # Virtex Temperature mask
C208_TEMPS_VIRTEX_TEMP_OFF = 0  # Virtex Temperature offset
C208_TEMPS_VREG_TEMP_MSK = 0x00007f00  # Voltage(2.5V,1.8V)reg. T mask
C208_TEMPS_VREG_TEMP_OFF = 8  # Voltage regulators T offset
C208_TEMPS_UMSK = 0x00007f7f  # Used bits mask

# ----------------------------------------------------------------------------
# Definitions for NIVEAU_OUT (output level) register(R/W).
# Remark: Better name for this register would be CHAN_TYPE!
# ----------------------------------------------------------------------------
# used bits mask
C208_NIVEAU_OUT_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
P201_NIVEAU_OUT_UMSK = 0x03000300

# ----------------------------------------------------------------------------
# Definitions for ADAPT_50 (en/disable 50 Ohm on input) register(R/W)
# ----------------------------------------------------------------------------
C208_ADAPT_50_UMSK = CT2_LO12BITS_MSK  # Used bits mask
P201_ADAPT_50_UMSK = CT2_LO10BITS_MSK  # Used bits mask

# ----------------------------------------------------------------------------
# Definitions for SOFT_OUT (soft output = like Digital Out) register(R/W)
# ----------------------------------------------------------------------------
C208_SOFT_OUT_UMSK = CT2_LO12BITS_MSK  # Used bits mask
P201_SOFT_OUT_UMSK = 0x00000300  # Used bits mask

# ----------------------------------------------------------------------------
# Definitions for RD_IN_OUT (Virtex I/O; like Digital IN) register(R)
# ----------------------------------------------------------------------------
# used bits mask
C208_RD_IN_OUT_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
P201_RD_IN_OUT_UMSK = 0x03000000 | CT2_LO10BITS_MSK
C208_RD_IN_OUT_INPUT_MSK = CT2_LO12BITS_MSK  # Input  level mask
P201_RD_IN_OUT_INPUT_MSK = CT2_LO10BITS_MSK  # Input  level mask
CT2_RD_IN_OUT_INPUT_OFF = 0  # Input  level offset
C208_RD_IN_OUT_OUTPUT_MSK = CT2_HI12BITS_MSK  # Output level mask
C208_RD_IN_OUT_OUTPUT_OFF = CT2_HI12BITS_OFF  # Output level offset
P201_RD_IN_OUT_OUTPUT_MSK = 0x03000000  # Output level mask
P201_RD_IN_OUT_OUTPUT_OFF = 24  # Output level offset

# ----------------------------------------------------------------------------
# Definitions for RD_CTRL_CMPT (counter run/enable status) register(R)
# ----------------------------------------------------------------------------
# used bits mask
CT2_RD_CTRL_CMPT_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
CT2_RD_CTRL_CMPT_ENDIS_MSK = CT2_LO12BITS_MSK  # counter soft en/disable
CT2_RD_CTRL_CMPT_ENDIS_OFF = CT2_LO12BITS_OFF
CT2_RD_CTRL_CMPT_ACQ_MSK = CT2_HI12BITS_MSK  # counter idle/running
CT2_RD_CTRL_CMPT_ACQ_OFF = CT2_HI12BITS_OFF

# ----------------------------------------------------------------------------
# Definitions for CMD_DMA (dma command) register(R/W)
# ----------------------------------------------------------------------------
# used bits mask
CT2_CMD_DMA_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK | 0x80000000
CT2_CMD_DMA_TRIG_MSK = CT2_LO12BITS_MSK  # DMA trigger condition
CT2_CMD_DMA_TRIG_OFF = CT2_LO12BITS_OFF  #     choice
CT2_CMD_DMA_TRANS_MSK = CT2_HI12BITS_MSK  # enable DMA transfer
CT2_CMD_DMA_TRANS_OFF = CT2_HI12BITS_OFF  #     choice
CT2_CMD_DMA_TRANSALL_BIT = 31  # 1: overall enable of DMA transf
#           (if this bit is not set the latches
#            selected in bits 16-27 are not
#            transferred).
# 0: reset FIFOs and error memory

# ----------------------------------------------------------------------------
# Definitions for CTRL_FIFO_DMA (dma control) register(R/W)
# ----------------------------------------------------------------------------
# used bits mask
CT2_CTRL_DMA_UMSK = CT2_LO12BITS_MSK | 0x001f0000
CT2_CTRL_DMA_NW_MSK = CT2_LO12BITS_MSK  # nb wrds in FIFO to rd
CT2_CTRL_DMA_NW_OFF = CT2_LO12BITS_OFF
CT2_CTRL_DMA_ERR_MSK = 0x00070000
CT2_CTRL_DMA_ERR_OFF = 16
CT2_CTRL_DMA_ERR_TRIG_LOST_BIT = 16  # 1: error one DMA trigger lost
CT2_CTRL_DMA_ERR_READ_FIFO_BIT = 17  # 1: error during FIFO read
CT2_CTRL_DMA_ERR_WRITE_FIFO_BIT = 18  # 1: error during FIFO write
CT2_CTRL_DMA_FLAGS_MSK = 0x00180000
CT2_CTRL_DMA_FLAGS_OFF = 19
CT2_CTRL_DMA_FIFO_EMPTY_BIT = 19  # 1: FIFO empty
CT2_CTRL_DMA_FIFO_FULL_BIT = 20  # 1: FIFO full

# ----------------------------------------------------------------------------
# Definitions for SOURCE_IT_A  register(R/W)
# ----------------------------------------------------------------------------
# used bits mask
C208_SRC_IT_A_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
P201_SRC_IT_A_UMSK = CT2_LO10BITS_MSK | CT2_HI10BITS_MSK
C208_SRC_IT_A_RE_MSK = CT2_LO12BITS_MSK  # IT src = Raising Edge
C208_SRC_IT_A_RE_OFF = CT2_LO12BITS_OFF
P201_SRC_IT_A_RE_MSK = CT2_LO10BITS_MSK  # IT src = Raising Edge
P201_SRC_IT_A_RE_OFF = CT2_LO10BITS_OFF
C208_SRC_IT_A_FE_MSK = CT2_HI12BITS_MSK  # IT src = Falling Edge
C208_SRC_IT_A_FE_OFF = CT2_HI12BITS_OFF
P201_SRC_IT_A_FE_MSK = CT2_HI10BITS_MSK  # IT src = Falling Edge
P201_SRC_IT_A_FE_OFF = CT2_HI10BITS_OFF

# ----------------------------------------------------------------------------
# Definitions for SOURCE_IT_B  register(R/W)
# ----------------------------------------------------------------------------
# used bits mask
CT2_SRC_IT_B_UMSK = CT2_LO12BITS_MSK | 0x00007000
CT2_SRC_IT_B_END_MSK = CT2_LO12BITS_MSK  # IT src = END of counter
CT2_SRC_IT_B_END_OFF = CT2_LO12BITS_OFF
CT2_SRC_IT_B_ENDFILL_BIT = 12  # IT at end of 1 cycle = 1 transfer of
#        selected latches into FIFO after DMA
#        trigger

CT2_SRC_IT_B_HALFFULL_BIT = 13  # IT at half fill FIFO after DMAtrig
CT2_SRC_IT_B_ERROR_BIT = 14  # IT due to error (see CTRL_FIFO_DMA)

# ----------------------------------------------------------------------------
# Definitions for CTRL_IT  register(R)
# ----------------------------------------------------------------------------
# used bits mask
C208_CTRL_IT_UMSK = 0x0effffff
P201_CTRL_IT_UMSK = 0x0efff3ff
C208_CTRL_IT_REFE_MSK = CT2_LO12BITS_MSK  # IT = Rais./Fall. Edge
C208_CTRL_IT_REFE_OFF = CT2_LO12BITS_OFF
P201_CTRL_IT_REFE_MSK = CT2_LO10BITS_MSK  # IT = Rais./Fall. Edge
P201_CTRL_IT_REFE_OFF = CT2_LO10BITS_OFF
CT2_CTRL_IT_END_MSK = 0x00fff000  # IT = END of ctn.0-11
CT2_CTRL_IT_END_OFF = 12
CT2_CTRL_IT_ENDFILL_BIT = 25  # IT at end of 1 cycle = 1 transfer of
#          selected latches into FIFO after DMA
#          trigger

CT2_CTRL_IT_HALFFULL_BIT = 26  # IT at half fill FIFO after DMA trig
CT2_CTRL_IT_ERROR_BIT = 27  # IT due to error (see CTRL_FIFO_DMA)

# ----------------------------------------------------------------------------
# Definitions for NIVEAU_IN register(R/W) - only exists for P201
# ----------------------------------------------------------------------------
P201_NIVEAU_IN_UMSK = CT2_LO10BITS_MSK | CT2_HI10BITS_MSK
P201_NIVEAU_IN_TTL_MSK = CT2_LO10BITS_MSK  # TTL in level mask
P201_NIVEAU_IN_TTL_OFF = CT2_LO10BITS_OFF
P201_NIVEAU_IN_NIM_MSK = CT2_HI10BITS_MSK  # NIM in level mask
P201_NIVEAU_IN_NIM_OFF = CT2_HI10BITS_OFF

P201_OUT_9_TTL_ENABLE = 1 << 8
P201_OUT_10_TTL_ENABLE = 1 << 9
P201_OUT_9_NIM_ENABLE = 1 << 24
P201_OUT_10_NIM_ENABLE = 1 << 25

# --------------------------------------------------------------------------
#                         PCI I/O Space 2 Registers
# --------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# Definitions for SEL_FILTRE_INPUT_A/B (input filter select) registers (R/W)
# ----------------------------------------------------------------------------
CT2_FILTRE_INPUT_UMSK = 0x3fffffff
CT2_FILTRE_INPUT_FREQ_FIELD_MSK = 0x7  # freq. bit field needs 3 bits
CT2_FILTRE_INPUT_ONECHAN_WIDTH = 5  # 5 bits cover input filter
#       selection for each channel
CT2_FILTRE_INPUT_FILT_MODE_OFF = 3  # offset of filter mode:
CT2_FILTRE_INPUT_FILT_MODE_SSPC = 0x0
CT2_FILTRE_INPUT_FILT_MODE_SYNC = 0x1
CT2_FILTRE_INPUT_FILT_MODE_SYM = 0x2
CT2_FILTRE_INPUT_FILT_MODE_ASYM = 0x3
CT2_FILTRE_INPUT_FILT_MODE_MSK = 0x3

# ----------------------------------------------------------------------------
# Definitions for SEL_FILTRE_OUTPUT_A/B/C (output filter select) regs (R/W)
# For P201 only the last (= the 3rd) output filter reg. is used
# ----------------------------------------------------------------------------
C208_FILTRE_OUTPUT_UMSK = 0x3fffffff  # used bits mask
P201_FILTRE_OUTPUT_UMSK = 0x00001f1f  # used bits mask
CT2_FILTRE_OUTPUT_FREQ_FIELD_MSK = 0x7  # freq bit field needs 3 bits
CT2_FILTRE_OUTPUT_ONECHAN_WIDTH = 5  # 5 bits cover input filter
#         selection for each channel
CT2_FILTRE_OUTPUT_FILTENAB_OFF = 3  # offset of filter en/disable
#         bit within 5 bits

CT2_FILTRE_OUTPUT_POLARITY_OFF = 4  # offset of polarity inversion
#         bit within 5 bits


@enum.unique
class FilterClock(enum.IntEnum):
    """Clock enumeration to be used in input and output filter configuration"""

    CLK_100_MHz = 0x0
    CLK_12_5_MHz = 0x1
    CLK_1_MHz = 0x2
    CLK_125_KHz = 0x3
    CLK_10_KHz = 0x4
    CLK_1_25_KHz = 0x5


@enum.unique
class FilterInputSelection(enum.IntEnum):
    """Input selection to be used in input filter configuration"""

    SINGLE_SHORT_PULSE_CAPTURE = 0 << 3
    SAMPLING_WITHOUT_FILTERING = 1 << 3
    SYMETRICAL_FILTER = 2 << 3
    ASYMETRICAL_FILTER = 3 << 3


# ----------------------------------------------------------------------------
# Definitions for SEL_SOURCE_OUTPUT_A/B/C (output source select) regs (R/W)
# For P201 only the last (= the 3rd) output source reg. is used
# ----------------------------------------------------------------------------
C208_SOURCE_OUTPUT_UMSK = 0x7f7f7f7f  # used bits mask
P201_SOURCE_OUTPUT_UMSK = 0x00007f7f  # used bits mask


@enum.unique
class OutputSrc(enum.IntEnum):
    """Output channel source enumeration"""

    SOFTWARE = 0x00
    CLK_1_25_KHz = 0x01
    CLK_10_KHz = 0x02
    CLK_125_KHz = 0x03
    CLK_1_MHz = 0x04
    CLK_12_5_MHz = 0x05
    CLK_DISABLE = 0x06

    CH_1_INPUT = 0x07
    CH_2_INPUT = 0x08
    CH_3_INPUT = 0x09
    CH_4_INPUT = 0x0A
    CH_5_INPUT = 0x0B
    CH_6_INPUT = 0x0C
    CH_7_INPUT = 0x0D
    CH_8_INPUT = 0x0E
    CH_9_INPUT = 0x0F
    CH_10_INPUT = 0x10

    CH_1_INPUT_INV = 0x13
    CH_2_INPUT_INV = 0x14
    CH_3_INPUT_INV = 0x15
    CH_4_INPUT_INV = 0x16
    CH_5_INPUT_INV = 0x17
    CH_6_INPUT_INV = 0x18
    CH_7_INPUT_INV = 0x19
    CH_8_INPUT_INV = 0x1A
    CH_9_INPUT_INV = 0x1B
    CH_10_INPUT_INV = 0x1C

    CH_1_RISING = 0x1F
    CH_2_RISING = 0x20
    CH_3_RISING = 0x21
    CH_4_RISING = 0x22
    CH_5_RISING = 0x23
    CH_6_RISING = 0x24
    CH_7_RISING = 0x25
    CH_8_RISING = 0x26
    CH_9_RISING = 0x27
    CH_10_RISING = 0x28

    CH_1_FALLING = 0x2B
    CH_2_FALLING = 0x2C
    CH_3_FALLING = 0x2D
    CH_4_FALLING = 0x2E
    CH_5_FALLING = 0x2F
    CH_6_FALLING = 0x30
    CH_7_FALLING = 0x31
    CH_8_FALLING = 0x32
    CH_9_FALLING = 0x33
    CH_10_FALLING = 0x34

    CH_1_RISING_FALLING = 0x37
    CH_2_RISING_FALLING = 0x38
    CH_3_RISING_FALLING = 0x39
    CH_4_RISING_FALLING = 0x3A
    CH_5_RISING_FALLING = 0x3B
    CH_6_RISING_FALLING = 0x3C
    CH_7_RISING_FALLING = 0x3D
    CH_8_RISING_FALLING = 0x3E
    CH_9_RISING_FALLING = 0x3F
    CH_10_RISING_FALLING = 0x40

    CT_1_START = 0x43
    CT_2_START = 0x44
    CT_3_START = 0x45
    CT_4_START = 0x46
    CT_5_START = 0x47
    CT_6_START = 0x48
    CT_7_START = 0x49
    CT_8_START = 0x4A
    CT_9_START = 0x4B
    CT_10_START = 0x4C
    CT_11_START = 0x4D
    CT_12_START = 0x4E

    CT_1_STOP = 0x4F
    CT_2_STOP = 0x50
    CT_3_STOP = 0x51
    CT_4_STOP = 0x52
    CT_5_STOP = 0x53
    CT_6_STOP = 0x54
    CT_7_STOP = 0x55
    CT_8_STOP = 0x56
    CT_9_STOP = 0x57
    CT_10_STOP = 0x58
    CT_11_STOP = 0x59
    CT_12_STOP = 0x5A

    CT_1_START_STOP = 0x5B
    CT_2_START_STOP = 0x5C
    CT_3_START_STOP = 0x5D
    CT_4_START_STOP = 0x5E
    CT_5_START_STOP = 0x5F
    CT_6_START_STOP = 0x60
    CT_7_START_STOP = 0x61
    CT_8_START_STOP = 0x62
    CT_9_START_STOP = 0x63
    CT_10_START_STOP = 0x64
    CT_11_START_STOP = 0x65
    CT_12_START_STOP = 0x66

    CT_1_GATE = 0x67
    CT_2_GATE = 0x68
    CT_3_GATE = 0x69
    CT_4_GATE = 0x6A
    CT_5_GATE = 0x6B
    CT_6_GATE = 0x6C
    CT_7_GATE = 0x6D
    CT_8_GATE = 0x6E
    CT_9_GATE = 0x6F
    CT_10_GATE = 0X70
    CT_11_GATE = 0x71
    CT_12_GATE = 0x72

    CT_1_SWITCH = 0x73
    CT_2_SWITCH = 0x74
    CT_3_SWITCH = 0x75
    CT_4_SWITCH = 0x76
    CT_5_SWITCH = 0x77
    CT_6_SWITCH = 0x78
    CT_7_SWITCH = 0x79
    CT_8_SWITCH = 0x7A
    CT_9_SWITCH = 0x7B
    CT_10_SWITCH = 0x7C
    CT_11_SWITCH = 0x7D
    CT_12_SWITCH = 0x7E

    DISABLE = 0x7F


# ----------------------------------------------------------------------------
# Definitions for SEL_LATCH_A/B/C/D/E/F (latch select) registers (R/W)
# ctn = [0,11] = counter number
# ----------------------------------------------------------------------------
# used bits mask
CT2_SEL_LATCH_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK


def CT2_SEL_LATCH_MSK(ctn):
    if ctn % 2:
        return CT2_LO12BITS_MSK
    return CT2_HI12BITS_MSK


def CT2_SEL_LATCH_OFF(ctn):
    if ctn % 2:
        return CT2_HI12BITS_OFF
    return CT2_HI12BITS_OFF


@enum.unique
class LatchCtSrc(enum.IntEnum):
    """
    Select counter source for latch
    """


# ----------------------------------------------------------------------------
# Definitions for CONF_CMPT_1/12 (counter configuration) registers (R/W)
# ----------------------------------------------------------------------------
CT2_CONF_CMPT_UMSK = 0xc7ffffff  # Used bits mask
CT2_CONF_CMPT_CLK_MSK = 0x0000007f
CT2_CONF_CMPT_CLK_OFF = 0
CT2_CONF_CMPT_CLK_100_MHz = 0x5
CT2_CONF_CMPT_GATE_MSK = 0x00001f80
CT2_CONF_CMPT_GATE_OFF = 7
CT2_CONF_CMPT_HSTART_MSK = 0x000fe000
CT2_CONF_CMPT_HSTART_OFF = 13
CT2_CONF_CMPT_HSTOP_MSK = 0x07f00000
CT2_CONF_CMPT_HSTOP_OFF = 20
CT2_CONF_CMPT_RESET_BIT = 30
CT2_CONF_CMPT_STOP_BIT = 31
CT2_CONF_CMPT_RESET_MSK = 1 << CT2_CONF_CMPT_RESET_BIT
CT2_CONF_CMPT_STOP_MSK = 1 << CT2_CONF_CMPT_STOP_BIT


@enum.unique
class CtClockSrc(enum.IntEnum):
    """
    Counts clock source enumeration. To be used in :class:`CtConfig`.
    """

    CLK_1_25_KHz = 0x00
    CLK_10_KHz = 0x01
    CLK_125_KHz = 0x02
    CLK_1_MHz = 0x03
    CLK_12_5_MHz = 0x04
    CLK_100_MHz = 0x05

    CH_1_RISING_EDGE = 0x06
    CH_2_RISING_EDGE = 0x07
    CH_3_RISING_EDGE = 0x08
    CH_4_RISING_EDGE = 0x09
    CH_5_RISING_EDGE = 0x0A
    CH_6_RISING_EDGE = 0x0B
    CH_7_RISING_EDGE = 0x0C
    CH_8_RISING_EDGE = 0x0D
    CH_9_RISING_EDGE = 0x0E
    CH_10_RISING_EDGE = 0x0F
    CH_11_RISING_EDGE = 0x10
    CH_12_RISING_EDGE = 0x11

    CH_1_FALLING_EDGE = 0x12
    CH_2_FALLING_EDGE = 0x13
    CH_3_FALLING_EDGE = 0x14
    CH_4_FALLING_EDGE = 0x15
    CH_5_FALLING_EDGE = 0x16
    CH_6_FALLING_EDGE = 0x17
    CH_7_FALLING_EDGE = 0x18
    CH_8_FALLING_EDGE = 0x19
    CH_9_FALLING_EDGE = 0x1A
    CH_10_FALLING_EDGE = 0x1B
    CH_11_FALLING_EDGE = 0x1C
    CH_12_FALLING_EDGE = 0x1D

    CH_1_RISING_FALLING_EDGE = 0x1E
    CH_2_RISING_FALLING_EDGE = 0x1F
    CH_3_RISING_FALLING_EDGE = 0x20
    CH_4_RISING_FALLING_EDGE = 0x21
    CH_5_RISING_FALLING_EDGE = 0x22
    CH_6_RISING_FALLING_EDGE = 0x23
    CH_7_RISING_FALLING_EDGE = 0x24
    CH_8_RISING_FALLING_EDGE = 0x25
    CH_9_RISING_FALLING_EDGE = 0X26
    CH_10_RISING_FALLING_EDGE = 0X27
    CH_11_RISING_FALLING_EDGE = 0x28
    CH_12_RISING_FALLING_EDGE = 0x29

    INC_CT_1_START = 0x2A
    INC_CT_2_START = 0x2B
    INC_CT_3_START = 0x2C
    INC_CT_4_START = 0x2D
    INC_CT_5_START = 0x2E
    INC_CT_6_START = 0x2F
    INC_CT_7_START = 0x30
    INC_CT_8_START = 0x31
    INC_CT_9_START = 0x32
    INC_CT_10_START = 0x33
    INC_CT_11_START = 0x34
    INC_CT_12_START = 0x35

    INC_CT_1_STOP = 0x36
    INC_CT_2_STOP = 0x37
    INC_CT_3_STOP = 0x38
    INC_CT_4_STOP = 0x39
    INC_CT_5_STOP = 0x3A
    INC_CT_6_STOP = 0x3B
    INC_CT_7_STOP = 0x3C
    INC_CT_8_STOP = 0x3D
    INC_CT_9_STOP = 0x3E
    INC_CT_10_STOP = 0x3F
    INC_CT_11_STOP = 0x40
    INC_CT_12_STOP = 0x41

    INC_CT_1_START_STOP = 0x42
    INC_CT_2_START_STOP = 0x43
    INC_CT_3_START_STOP = 0x44
    INC_CT_4_START_STOP = 0x45
    INC_CT_5_START_STOP = 0x46
    INC_CT_6_START_STOP = 0x47
    INC_CT_7_START_STOP = 0x48
    INC_CT_8_START_STOP = 0x49
    INC_CT_9_START_STOP = 0x4A
    INC_CT_10_START_STOP = 0x4B
    INC_CT_11_START_STOP = 0x4C
    INC_CT_12_START_STOP = 0x4D

    INC_CH_1_PULSE = 0x4E
    INC_CH_2_PULSE = 0x4F
    INC_CH_3_PULSE = 0x50
    INC_CH_4_PULSE = 0x51
    INC_CH_5_PULSE = 0x52
    INC_CH_6_PULSE = 0x53
    INC_CH_7_PULSE = 0x54
    INC_CH_8_PULSE = 0x55
    INC_CH_9_PULSE = 0x56
    INC_CH_10_PULSE = 0x57
    INC_CH_11_PULSE = 0x58
    INC_CH_12_PULSE = 0x59


@enum.unique
class CtGateSrc(enum.IntEnum):
    """Couter Gate source enumeration. To be used in :class:`CtConfig`."""

    GATE_CMPT = 0x00 << CT2_CONF_CMPT_GATE_OFF

    CH_1_INPUT = 0x01 << CT2_CONF_CMPT_GATE_OFF
    CH_2_INPUT = 0x02 << CT2_CONF_CMPT_GATE_OFF
    CH_3_INPUT = 0x03 << CT2_CONF_CMPT_GATE_OFF
    CH_4_INPUT = 0x04 << CT2_CONF_CMPT_GATE_OFF
    CH_5_INPUT = 0x05 << CT2_CONF_CMPT_GATE_OFF
    CH_6_INPUT = 0x06 << CT2_CONF_CMPT_GATE_OFF
    CH_7_INPUT = 0x07 << CT2_CONF_CMPT_GATE_OFF
    CH_8_INPUT = 0x08 << CT2_CONF_CMPT_GATE_OFF
    CH_9_INPUT = 0x09 << CT2_CONF_CMPT_GATE_OFF
    CH_10_INPUT = 0x0A << CT2_CONF_CMPT_GATE_OFF

    CH_1_INPUT_INV = 0x0D << CT2_CONF_CMPT_GATE_OFF
    CH_2_INPUT_INV = 0x0E << CT2_CONF_CMPT_GATE_OFF
    CH_3_INPUT_INV = 0x0F << CT2_CONF_CMPT_GATE_OFF
    CH_4_INPUT_INV = 0x10 << CT2_CONF_CMPT_GATE_OFF
    CH_5_INPUT_INV = 0x11 << CT2_CONF_CMPT_GATE_OFF
    CH_6_INPUT_INV = 0x12 << CT2_CONF_CMPT_GATE_OFF
    CH_7_INPUT_INV = 0x13 << CT2_CONF_CMPT_GATE_OFF
    CH_8_INPUT_INV = 0x14 << CT2_CONF_CMPT_GATE_OFF
    CH_9_INPUT_INV = 0x15 << CT2_CONF_CMPT_GATE_OFF
    CH_10_INPUT_INV = 0x16 << CT2_CONF_CMPT_GATE_OFF

    CT_1_GATE_ENVELOP = 0x19 << CT2_CONF_CMPT_GATE_OFF
    CT_2_GATE_ENVELOP = 0x1A << CT2_CONF_CMPT_GATE_OFF
    CT_3_GATE_ENVELOP = 0x1B << CT2_CONF_CMPT_GATE_OFF
    CT_4_GATE_ENVELOP = 0x1C << CT2_CONF_CMPT_GATE_OFF
    CT_5_GATE_ENVELOP = 0x1D << CT2_CONF_CMPT_GATE_OFF
    CT_6_GATE_ENVELOP = 0x1E << CT2_CONF_CMPT_GATE_OFF
    CT_7_GATE_ENVELOP = 0x1F << CT2_CONF_CMPT_GATE_OFF
    CT_8_GATE_ENVELOP = 0x20 << CT2_CONF_CMPT_GATE_OFF
    CT_9_GATE_ENVELOP = 0x21 << CT2_CONF_CMPT_GATE_OFF
    CT_10_GATE_ENVELOP = 0x22 << CT2_CONF_CMPT_GATE_OFF
    CT_11_GATE_ENVELOP = 0x23 << CT2_CONF_CMPT_GATE_OFF
    CT_12_GATE_ENVELOP = 0x24 << CT2_CONF_CMPT_GATE_OFF

    CT_1_SWITCH_SIGNAL = 0x25 << CT2_CONF_CMPT_GATE_OFF
    CT_2_SWITCH_SIGNAL = 0x26 << CT2_CONF_CMPT_GATE_OFF
    CT_3_SWITCH_SIGNAL = 0x27 << CT2_CONF_CMPT_GATE_OFF
    CT_4_SWITCH_SIGNAL = 0x28 << CT2_CONF_CMPT_GATE_OFF
    CT_5_SWITCH_SIGNAL = 0x29 << CT2_CONF_CMPT_GATE_OFF
    CT_6_SWITCH_SIGNAL = 0x2A << CT2_CONF_CMPT_GATE_OFF
    CT_7_SWITCH_SIGNAL = 0x2B << CT2_CONF_CMPT_GATE_OFF
    CT_8_SWITCH_SIGNAL = 0x2C << CT2_CONF_CMPT_GATE_OFF
    CT_9_SWITCH_SIGNAL = 0x2D << CT2_CONF_CMPT_GATE_OFF
    CT_10_SWITCH_SIGNAL = 0x2E << CT2_CONF_CMPT_GATE_OFF
    CT_11_SWITCH_SIGNAL = 0x2F << CT2_CONF_CMPT_GATE_OFF
    CT_12_SWITCH_SIGNAL = 0x30 << CT2_CONF_CMPT_GATE_OFF


@enum.unique
class CtHardStartSrc(enum.IntEnum):
    """Couter hardware start source enumeration. To be used in :class:`CtConfig`."""

    SOFTWARE = 0x00 << CT2_CONF_CMPT_HSTART_OFF

    CH_1_RISING_EDGE = 0x01 << CT2_CONF_CMPT_HSTART_OFF
    CH_2_RISING_EDGE = 0x02 << CT2_CONF_CMPT_HSTART_OFF
    CH_3_RISING_EDGE = 0x03 << CT2_CONF_CMPT_HSTART_OFF
    CH_4_RISING_EDGE = 0x04 << CT2_CONF_CMPT_HSTART_OFF
    CH_5_RISING_EDGE = 0x05 << CT2_CONF_CMPT_HSTART_OFF
    CH_6_RISING_EDGE = 0x06 << CT2_CONF_CMPT_HSTART_OFF
    CH_7_RISING_EDGE = 0x07 << CT2_CONF_CMPT_HSTART_OFF
    CH_8_RISING_EDGE = 0x08 << CT2_CONF_CMPT_HSTART_OFF
    CH_9_RISING_EDGE = 0x09 << CT2_CONF_CMPT_HSTART_OFF
    CH_10_RISING_EDGE = 0x0A << CT2_CONF_CMPT_HSTART_OFF

    CH_1_FALLING_EDGE = 0x0D << CT2_CONF_CMPT_HSTART_OFF
    CH_2_FALLING_EDGE = 0x0E << CT2_CONF_CMPT_HSTART_OFF
    CH_3_FALLING_EDGE = 0x0F << CT2_CONF_CMPT_HSTART_OFF
    CH_4_FALLING_EDGE = 0x10 << CT2_CONF_CMPT_HSTART_OFF
    CH_5_FALLING_EDGE = 0x11 << CT2_CONF_CMPT_HSTART_OFF
    CH_6_FALLING_EDGE = 0x12 << CT2_CONF_CMPT_HSTART_OFF
    CH_7_FALLING_EDGE = 0x13 << CT2_CONF_CMPT_HSTART_OFF
    CH_8_FALLING_EDGE = 0x14 << CT2_CONF_CMPT_HSTART_OFF
    CH_9_FALLING_EDGE = 0x15 << CT2_CONF_CMPT_HSTART_OFF
    CH_10_FALLING_EDGE = 0x16 << CT2_CONF_CMPT_HSTART_OFF

    CH_1_RISING_FALLING_EDGE = 0x19 << CT2_CONF_CMPT_HSTART_OFF
    CH_2_RISING_FALLING_EDGE = 0x1A << CT2_CONF_CMPT_HSTART_OFF
    CH_3_RISING_FALLING_EDGE = 0x1B << CT2_CONF_CMPT_HSTART_OFF
    CH_4_RISING_FALLING_EDGE = 0x1C << CT2_CONF_CMPT_HSTART_OFF
    CH_5_RISING_FALLING_EDGE = 0x1D << CT2_CONF_CMPT_HSTART_OFF
    CH_6_RISING_FALLING_EDGE = 0x1E << CT2_CONF_CMPT_HSTART_OFF
    CH_7_RISING_FALLING_EDGE = 0x1F << CT2_CONF_CMPT_HSTART_OFF
    CH_8_RISING_FALLING_EDGE = 0x20 << CT2_CONF_CMPT_HSTART_OFF
    CH_9_RISING_FALLING_EDGE = 0X21 << CT2_CONF_CMPT_HSTART_OFF
    CH_10_RISING_FALLING_EDGE = 0x22 << CT2_CONF_CMPT_HSTART_OFF

    CT_1_START = 0x25 << CT2_CONF_CMPT_HSTART_OFF
    CT_2_START = 0x26 << CT2_CONF_CMPT_HSTART_OFF
    CT_3_START = 0x27 << CT2_CONF_CMPT_HSTART_OFF
    CT_4_START = 0x28 << CT2_CONF_CMPT_HSTART_OFF
    CT_5_START = 0x29 << CT2_CONF_CMPT_HSTART_OFF
    CT_6_START = 0x2A << CT2_CONF_CMPT_HSTART_OFF
    CT_7_START = 0x2B << CT2_CONF_CMPT_HSTART_OFF
    CT_8_START = 0x2C << CT2_CONF_CMPT_HSTART_OFF
    CT_9_START = 0x2D << CT2_CONF_CMPT_HSTART_OFF
    CT_10_START = 0x2E << CT2_CONF_CMPT_HSTART_OFF
    CT_11_START = 0x2F << CT2_CONF_CMPT_HSTART_OFF
    CT_12_START = 0x30 << CT2_CONF_CMPT_HSTART_OFF

    CT_1_STOP = 0x31 << CT2_CONF_CMPT_HSTART_OFF
    CT_2_STOP = 0x32 << CT2_CONF_CMPT_HSTART_OFF
    CT_3_STOP = 0x33 << CT2_CONF_CMPT_HSTART_OFF
    CT_4_STOP = 0x34 << CT2_CONF_CMPT_HSTART_OFF
    CT_5_STOP = 0x35 << CT2_CONF_CMPT_HSTART_OFF
    CT_6_STOP = 0x36 << CT2_CONF_CMPT_HSTART_OFF
    CT_7_STOP = 0x37 << CT2_CONF_CMPT_HSTART_OFF
    CT_8_STOP = 0x38 << CT2_CONF_CMPT_HSTART_OFF
    CT_9_STOP = 0x39 << CT2_CONF_CMPT_HSTART_OFF
    CT_10_STOP = 0x3A << CT2_CONF_CMPT_HSTART_OFF
    CT_11_STOP = 0x3B << CT2_CONF_CMPT_HSTART_OFF
    CT_12_STOP = 0x3C << CT2_CONF_CMPT_HSTART_OFF

    CT_1_START_STOP = 0x3D << CT2_CONF_CMPT_HSTART_OFF
    CT_2_START_STOP = 0x3E << CT2_CONF_CMPT_HSTART_OFF
    CT_3_START_STOP = 0x3F << CT2_CONF_CMPT_HSTART_OFF
    CT_4_START_STOP = 0x40 << CT2_CONF_CMPT_HSTART_OFF
    CT_5_START_STOP = 0x41 << CT2_CONF_CMPT_HSTART_OFF
    CT_6_START_STOP = 0x42 << CT2_CONF_CMPT_HSTART_OFF
    CT_7_START_STOP = 0x43 << CT2_CONF_CMPT_HSTART_OFF
    CT_8_START_STOP = 0x44 << CT2_CONF_CMPT_HSTART_OFF
    CT_9_START_STOP = 0x45 << CT2_CONF_CMPT_HSTART_OFF
    CT_10_START_STOP = 0x46 << CT2_CONF_CMPT_HSTART_OFF
    CT_11_START_STOP = 0x47 << CT2_CONF_CMPT_HSTART_OFF
    CT_12_START_STOP = 0x48 << CT2_CONF_CMPT_HSTART_OFF

    CT_1_EQ_CMP_1 = 0x49 << CT2_CONF_CMPT_HSTART_OFF
    CT_2_EQ_CMP_2 = 0x4A << CT2_CONF_CMPT_HSTART_OFF
    CT_3_EQ_CMP_3 = 0x4B << CT2_CONF_CMPT_HSTART_OFF
    CT_4_EQ_CMP_4 = 0x4C << CT2_CONF_CMPT_HSTART_OFF
    CT_5_EQ_CMP_5 = 0x4D << CT2_CONF_CMPT_HSTART_OFF
    CT_6_EQ_CMP_6 = 0x4E << CT2_CONF_CMPT_HSTART_OFF
    CT_7_EQ_CMP_7 = 0x4F << CT2_CONF_CMPT_HSTART_OFF
    CT_8_EQ_CMP_8 = 0x50 << CT2_CONF_CMPT_HSTART_OFF
    CT_9_EQ_CMP_9 = 0x51 << CT2_CONF_CMPT_HSTART_OFF
    CT_10_EQ_CMP_10 = 0x52 << CT2_CONF_CMPT_HSTART_OFF
    CT_11_EQ_CMP_11 = 0x53 << CT2_CONF_CMPT_HSTART_OFF
    CT_12_EQ_CMP_12 = 0x54 << CT2_CONF_CMPT_HSTART_OFF


@enum.unique
class CtHardStopSrc(enum.IntEnum):
    """Couter hardware stop source enumeration. To be used in :class:`CtConfig`."""

    SOFTWARE = 0x00 << CT2_CONF_CMPT_HSTOP_OFF

    CH_1_RISING_EDGE = 0x01 << CT2_CONF_CMPT_HSTOP_OFF
    CH_2_RISING_EDGE = 0x02 << CT2_CONF_CMPT_HSTOP_OFF
    CH_3_RISING_EDGE = 0x03 << CT2_CONF_CMPT_HSTOP_OFF
    CH_4_RISING_EDGE = 0x04 << CT2_CONF_CMPT_HSTOP_OFF
    CH_5_RISING_EDGE = 0x05 << CT2_CONF_CMPT_HSTOP_OFF
    CH_6_RISING_EDGE = 0x06 << CT2_CONF_CMPT_HSTOP_OFF
    CH_7_RISING_EDGE = 0x07 << CT2_CONF_CMPT_HSTOP_OFF
    CH_8_RISING_EDGE = 0x08 << CT2_CONF_CMPT_HSTOP_OFF
    CH_9_RISING_EDGE = 0x09 << CT2_CONF_CMPT_HSTOP_OFF
    CH_10_RISING_EDGE = 0x0A << CT2_CONF_CMPT_HSTOP_OFF

    CH_1_FALLING_EDGE = 0x0D << CT2_CONF_CMPT_HSTOP_OFF
    CH_2_FALLING_EDGE = 0x0E << CT2_CONF_CMPT_HSTOP_OFF
    CH_3_FALLING_EDGE = 0x0F << CT2_CONF_CMPT_HSTOP_OFF
    CH_4_FALLING_EDGE = 0x10 << CT2_CONF_CMPT_HSTOP_OFF
    CH_5_FALLING_EDGE = 0x11 << CT2_CONF_CMPT_HSTOP_OFF
    CH_6_FALLING_EDGE = 0x12 << CT2_CONF_CMPT_HSTOP_OFF
    CH_7_FALLING_EDGE = 0x13 << CT2_CONF_CMPT_HSTOP_OFF
    CH_8_FALLING_EDGE = 0x14 << CT2_CONF_CMPT_HSTOP_OFF
    CH_9_FALLING_EDGE = 0x15 << CT2_CONF_CMPT_HSTOP_OFF
    CH_10_FALLING_EDGE = 0x16 << CT2_CONF_CMPT_HSTOP_OFF

    CH_1_RISING_FALLING_EDGE = 0x19 << CT2_CONF_CMPT_HSTOP_OFF
    CH_2_RISING_FALLING_EDGE = 0x1A << CT2_CONF_CMPT_HSTOP_OFF
    CH_3_RISING_FALLING_EDGE = 0x1B << CT2_CONF_CMPT_HSTOP_OFF
    CH_4_RISING_FALLING_EDGE = 0x1C << CT2_CONF_CMPT_HSTOP_OFF
    CH_5_RISING_FALLING_EDGE = 0x1D << CT2_CONF_CMPT_HSTOP_OFF
    CH_6_RISING_FALLING_EDGE = 0x1E << CT2_CONF_CMPT_HSTOP_OFF
    CH_7_RISING_FALLING_EDGE = 0x1F << CT2_CONF_CMPT_HSTOP_OFF
    CH_8_RISING_FALLING_EDGE = 0x20 << CT2_CONF_CMPT_HSTOP_OFF
    CH_9_RISING_FALLING_EDGE = 0X21 << CT2_CONF_CMPT_HSTOP_OFF
    CH_10_RISING_FALLING_EDGE = 0x22 << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_START = 0x25 << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_START = 0x26 << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_START = 0x27 << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_START = 0x28 << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_START = 0x29 << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_START = 0x2A << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_START = 0x2B << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_START = 0x2C << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_START = 0x2D << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_START = 0x2E << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_START = 0x2F << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_START = 0x30 << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_STOP = 0x31 << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_STOP = 0x32 << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_STOP = 0x33 << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_STOP = 0x34 << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_STOP = 0x35 << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_STOP = 0x36 << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_STOP = 0x37 << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_STOP = 0x38 << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_STOP = 0x39 << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_STOP = 0x3A << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_STOP = 0x3B << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_STOP = 0x3C << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_START_STOP = 0x3D << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_START_STOP = 0x3E << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_START_STOP = 0x3F << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_START_STOP = 0x40 << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_START_STOP = 0x41 << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_START_STOP = 0x42 << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_START_STOP = 0x43 << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_START_STOP = 0x44 << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_START_STOP = 0x45 << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_START_STOP = 0x46 << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_START_STOP = 0x47 << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_START_STOP = 0x48 << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_EQ_CMP_1 = 0x49 << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_EQ_CMP_2 = 0x4A << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_EQ_CMP_3 = 0x4B << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_EQ_CMP_4 = 0x4C << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_EQ_CMP_5 = 0x4D << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_EQ_CMP_6 = 0x4E << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_EQ_CMP_7 = 0x4F << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_EQ_CMP_8 = 0x50 << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_EQ_CMP_9 = 0x51 << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_EQ_CMP_10 = 0x52 << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_EQ_CMP_11 = 0x53 << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_EQ_CMP_12 = 0x54 << CT2_CONF_CMPT_HSTOP_OFF


# ----------------------------------------------------------------------------
# Definitions for SOFT_ENABLE_DISABLE register (W)
# reg = value of soft_enable_disable register, ctn = [0,11] = counter number
# ----------------------------------------------------------------------------
# used bits mask
CT2_SOFT_ENABLE_DISABLE_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
CT2_SOFT_ENABLE_ALL_MSK = CT2_LO12BITS_MSK
CT2_SOFT_ENABLE_ALL_OFF = CT2_LO12BITS_OFF
CT2_SOFT_DISABLE_ALL_MSK = CT2_HI12BITS_MSK
CT2_SOFT_DISABLE_ALL_OFF = CT2_HI12BITS_OFF


def CT2_SOFT_ENABLE(reg, ctn):
    return BIT_SETB(reg, ctn)


def CT2_SOFT_DISABLE(reg, ctn):
    return BIT_SETB(reg, ctn + 16)


# ----------------------------------------------------------------------------
# Definitions for SOFT_START_STOP register (W)
# reg = value of soft_start_stop register, crn = [0,11] = counter number
# ----------------------------------------------------------------------------
# used bits mask
CT2_SOFT_START_STOP_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
CT2_SOFT_START_ALL_MSK = CT2_LO12BITS_MSK
CT2_SOFT_START_ALL_OFF = CT2_LO12BITS_OFF
CT2_SOFT_STOP_ALL_MSK = CT2_HI12BITS_MSK
CT2_SOFT_STOP_ALL_OFF = CT2_HI12BITS_OFF


def CT2_SOFT_START(reg, ctn):
    return BIT_SETB(reg, ctn)


def CT2_SOFT_STOP(reg, ctn):
    return BIT_SETB(reg, ctn + 16)


# ----------------------------------------------------------------------------
# Definitions for SOFT_LATCH register (W)
# reg = value of soft_latch register, ctn = [0,11] = counter number
# ----------------------------------------------------------------------------
# used bits mask
CT2_SOFT_LATCH_UMSK = CT2_LO12BITS_MSK
CT2_SOFT_LATCH_ALL_MSK = CT2_LO12BITS_MSK
CT2_SOFT_LATCH_ALL_OFF = CT2_LO12BITS_OFF


def CT2_SOFT_LATCH(reg, ctn):
    return BIT_SETB(reg, ctn)


# XXX

# CT2_NREGS_SOURCE_IT     =            (ct2_reg_size(1, source_it))
# CT2_NREGS_RD_CMPT       =            (ct2_reg_size(1, rd_cmpt))
# CT2_NREGS_RD_LATCH_CMPT =            (ct2_reg_size(1, rd_latch_cmpt))

# CT2_NREGS_SEL_FILTRE_INPUT =         (ct2_reg_size(2, sel_filtre_input))
# CT2_NREGS_SEL_FILTRE_OUTPUT_C208 =   (ct2_reg_size(2, c208_sel_filtre_output))
# CT2_NREGS_SEL_FILTRE_OUTPUT_P201 =   (ct2_reg_size(2, p201_sel_filtre_output))
# CT2_NREGS_SEL_SOURCE_OUTPUT_C208 =   (ct2_reg_size(2, c208_sel_source_output))
# CT2_NREGS_SEL_SOURCE_OUTPUT_P201 =   (ct2_reg_size(2, p201_sel_source_output))
# CT2_NREGS_SEL_LATCH =                (ct2_reg_size(2, sel_latch))
# CT2_NREGS_CONF_CMPT =                (ct2_reg_size(2, conf_cmpt))
# CT2_NREGS_COMPARE_CMPT =             (ct2_reg_size(2, compare_cmpt))

#: Access to the Scaler Values FIFO is provided via the same (p)read(v)(2)
#: and lseek(2) system calls than the PCI I/O Register Maps, with an offset
#: just after the second register map

CT2_RW_R1_OFF = 0
CT2_RW_R2_OFF = 64
CT2_RW_R1_LEN = CT2_RW_R2_OFF - CT2_RW_R1_OFF
CT2_RW_R2_LEN = 64

CT2_RW_FIFO_OFF = CT2_RW_R2_OFF + CT2_RW_R2_LEN
CT2_RW_FIFO_LEN = 2 * 1024


#: Access to the Scaler Values FIFO of a Dev. is also provided via the  mmap(2)
#: system call on the open file description obtained from an  open(2)  on the
#: character special file associated with the Device.  The FIFO is mapped
#: neither for writing nor execution into the mmap Device space embedded
#: within the type of the  offset  argument to  mmap(2)  beginning at
#: CT2_FIFO_MMAP_OFF  page size unit bytes for as many bytes as the
#: Device says its FIFO is large (+).
#:
#: In order for userland to successfully  mmap(2)  the FIFO of a Device,
#: exclusive access to the Device must have been obtained, otherwise the call
#: will fail with  errno  set to  EACCES.  The call will also fail, with  errno
#: set to  EINVAL, if any of the  length  or  offset  arguments is invalid w.r.t.
#: the region within the mmap Device space as defined above or if it is to be
#: mapped for writing or execution.
#:
#: NOTE: As long as there exists at least one mapping of the FIFO into
#:       userspace, every attempt to  close(2)  the open file description
#:       that was used to obtain the initial mapping will fail with
#:       errno  set to  EBUSY.
#:
#: (+) This information may be obtained from the sysfs entry to the
#:     PCI node of the Device.
#:
CT2_MM_FIFO_OFF = 0

CT2_IOC_MAGIC = ord("w")

__CT2_BASE_ERRORS = {
    errno.EACCES: "Failed to {operation}: exclusive access was set up "
    "previously for the device, but for a different open "
    "file description than the one in the request",
    errno.EBUSY: "Failed to {operation}: interrupts are still enabled",
    errno.EINTR: "Failed to {operation} : interrupted while waiting for "
    "permission to exclusively access the device",
    errno.EINVAL: "Failed to {operation}: invalid arguments",
    errno.ENOMEM: "Failed to {operation}: could not allocate storage "
    "for the notification queue (file descriptor in blocking "
    "mode)",
    errno.EAGAIN: "Failed to {operation}: could not allocate storage for "
    "the notification queue (file descriptor in non blocking "
    "mode)",
    errno.EFAULT: "Failed to {operation}: invalid argument",
    errno.ENXIO: "Failed to {operation}: detected an attached INQ to the "
    "description of the request although INQs are not "
    "implemented",
    errno.ENOSYS: "Failed to {operation}: not implemented",
}


def __CT2_ERRORS(operation, new_errors=None):
    errors = {}
    for err_no, err_desc in list(__CT2_BASE_ERRORS.items()):
        errors[err_no] = err_desc.format(operation=operation)
    if new_errors:
        errors.update(new_errors)
    return errors


#: CT2_IOC_QXA - "re[Q]uesting e[X]clusive device [A]ccess"
#:
#: arguments:
#:
#:  -
#:
#: Request exclusive access for the open file description in the call.
#:
#: returns:
#:
#:  zero on success
#:  non-zero on failure with  errno  set appropriately:
#:
#:    EACCES  exclusive access was set up previously for the Device, but for
#:            a different open file description than the one in the request
#:
#:    EINTR   the caller was interrupted while waiting for permission to
#:            exclusively access the Device
#:
#:    EINVAL  some arguments to the  ioctl(2)  call where invalid
#:
CT2_IOC_QXA = (
    _IO(CT2_IOC_MAGIC, 21),
    "CT2_IOC_QXA",
    __CT2_ERRORS("request exclusive_access"),
)


#: CT2_IOC_LXA - "re[L]inquishing e[X]clusive device [A]ccess"
#:
#: arguments:
#:
#:  -
#:
#: Give up exclusive access for the open file description in the call,
#: ignoring the request if there was no exclusive Device access granted
#: at all.
#:
#: returns:
#:
#:  zero on success
#:  non-zero on failure with  errno  set appropriately:
#:
#:    EACCES  exclusive access was set up previously for the Device, but for
#:            a different open file description than the one in the request
#:
#:    EBUSY   at least one  mmap(2)  of the Scaler Values FIFO was still active
#:
#:    EINTR   the caller was interrupted while waiting for permission to
#:            exclusively access the Device
#:
#:    EINVAL  some arguments to the  ioctl(2)  call where invalid
#:
CT2_IOC_LXA = (
    _IO(CT2_IOC_MAGIC, 22),
    "CT2_IOC_LXA",
    __CT2_ERRORS(
        "relinquish exclusive_access",
        {
            errno.EBUSY: "Failed to relinquish exclusive access: "
            "at least one mmap is still active"
        },
    ),
)


#: CT2_IOC_DEVRST - "[DEV]ice [R]e[S]e[T]"
#:
#: arguments:
#:
#:  -
#:
#: A "Device Reset" shall be defined as the following sequence of operations on
#: the device where we provide a value for every register in the memory sense of
#: the word that can be written to.
#:
#:  1.  disable the generation of interrupts
#:  2.  disable output drivers/stages, ie enable their high impedance state (XXX)
#:  3.  a.  remove the input load from the input stages,
#:      b.  set the input filter master clock frequency divider to (the default of) "1",
#:          capture synchronously but bypass the input filters, and,
#:      c.  on the P201, disable the inputs altogether (XXX)
#:  4.  a.  set the output filter master clock frequency divider to (the default of) "1",
#:          bypass the output filter,
#:          set the output value polarity to "normal", and
#:      b.  fix the output logic value to "0"
#:  5.  set the programmable output logic level to "0"
#:  6.  inhibit any Device internal data movement of the Scaler Values FIFO,
#:      flush the FIFO, and clear FIFO error flags
#:  7.  set the counter clock source to (the default of) the master clock,
#:      open the counter clock gate wide, and
#:      disconnect any internally wired counter control connections
#:  8.  inhibit storage of the counter value in each CCL unit's latch
#:  9.  clear each CCL unit's comparator latch and counter
#: 10.  disable the master clock and
#:      set the clock frequency selector to (the default of) "100 MHz"
#:
#: NOTE: Since we must regard the generation and acknowledgement of interrupts
#:       as state changing operations, and the whole purpose of a general Device
#:       reset is to arrive at a known state, we require that the generation of
#:       interrupts be /disabled/ during the reset.
#:
#: returns:
#:
#:  zero on success
#:  non-zero on failure with  errno  set appropriately:
#:
#:    EACCES  exclusive access was set up previously for the Device, but for
#:            a different open file description than the one in the request
#:
#:    EBUSY   interrupts are still enabled, preventing the request to be
#:            processed
#:
#:    EINTR   the caller was interrupted while waiting for permission to
#:            exclusively access the Device
#:
#:    EINVAL  some arguments to the  ioctl(2)  call where invalid
#:
CT2_IOC_DEVRST = _IO(CT2_IOC_MAGIC, 0), "CT2_IOC_DEVRST", __CT2_ERRORS("reset card")


#: CT2_IOC_EDINT - "[E]nable [D]evice [INT]errupts"
#:
#: arguments:
#:
#: - capacity of the interrupt notification queue
#:
#: Have the Operating System set up everything associated with the Device
#: that is required so that we can receive Device interrupts once we enable
#: their generation at the Device proper via SOURCE_IT_A/B.
#:
#: In order to not lose any notification of such interrupts, a queue is set
#: up between the actual interrupt handler and the context that eventually
#: makes them available to interested listeners whose capacity must be given
#: as the argument.  Here, a value of  0  means that the default as determined
#: by the module parameter "inq_length" shall be used for the capacity of
#: the queue.
#:
#: If interrupts are already enabled with a queue capacity  c, the request
#: to re-enable them with a queue capacity  d  will be considered a success
#: without actually performing the required actions if both  c  and  d  are
#: equal and an error otherwise.
#:
#: returns:
#:
#: - zero on success
#: - non-zero on failure with  errno  set appropriately:
#:
#:    - EACCES: exclusive access was set up previously for the Device, but for
#:      a different open file description than the one in the request
#:
#:    - EBUSY: interrupts are already enabled with a queue capacity different
#:      from the one in the argument of the request
#:
#:    - ENOMEM: failure to allocate storage for the notification queue and
#:      the open file description in the request was in blocking mode
#:
#:    - EAGAIN: similar to the ENOMEM case, only that the open file description
#:      in the request was in non-blocking mode
#:
#:    - EINTR: the caller was interrupted while waiting for permission to
#:      exclusively access the Device
#:
#:    - EINVAL: some arguments to the  ioctl(2)  call where invalid
#:
CT2_IOC_EDINT = (
    _IOW(CT2_IOC_MAGIC, 0o1, CT2_SIZE),
    "CT2_IOC_EDINT",
    __CT2_ERRORS(
        "enable interrupts",
        {
            errno.EBUSY: "Failed to enable interrupts: interrupts are already "
            "enabled with a queue with a different capacity"
        },
    ),
)


#: CT2_IOC_DDINT - "[D]isable [D]evice [INT]errupts"
#:
#: arguments:
#:
#:  -
#:
#: Undo everything that was set up during a (previous) CT2_IOC_EDINT call,
#: ignoring the request if interrupts are already disabled.
#:
#: NOTE: No attempts are being made in ensuring that the Device itself
#:       actually ceased to generate interrupts.  Failure to observe this
#:       will most likely result in the kernel complaining about interrupts
#:       "nobody cared" for etcpp.
#:
#: returns:
#:
#:  zero on success
#:  non-zero on failure with  errno  set appropriately:
#:
#:    EACCES  exclusive access was set up previously for the Device, but for
#:            a different open file description than the one in the request
#:
#:    EINTR   the caller was interrupted while waiting for permission to
#:            exclusively access the Device
#:
#:    EINVAL  some arguments to the  ioctl(2)  call where invalid
#:
CT2_IOC_DDINT = (
    _IO(CT2_IOC_MAGIC, 0o2),
    "CT2_IOC_DDINT",
    __CT2_ERRORS("disable interrupts"),
)


#: CT2_IOC_ACKINT - "[ACK]nowledge [INT]errupt"
#:
#: arguments:
#:
#:  1:  pointer to an interrupt notification object
#:
#: Obtain the accumulation of all delivered interrupt notifications since the
#: last successful CT2_IOC_ACKINT call prior to the current request along with
#: the time the most recent delivery occurred, clearing  CTRL_IT  in the
#: interrupt notification storage and updating its time to the time of
#: the current request.  The time is obtained from the clock with ID
#: CLOCK_MONOTONIC_RAW.
#:
#: A value of  0  in  ctrl_it  of the object the argument points to indicates
#: that there were no new interrupt notifications while a non-zero value hints
#: at the delivery of at least one such notification.  In the former case, the
#: stamp  member contains the time the value of  CTRL_IT  in the interrupt
#: notification storage was last read while in the latter, the time  CTRL_IT
#: was last updated is saved.
#:
#: returns:
#:
#:  zero on success
#:  non-zero on failure with  errno  set appropriately:
#:
#:    EFAULT  the argument of the request does not point into a valid
#:            object of type  struct ct2_in  in the calling user context's
#:            address space
#:
#:    EINTR   the caller was interrupted while waiting for permission to
#:            exclusively access the Device
#:
#:    EINVAL  some arguments to the  ioctl(2)  call where invalid
#:
#:    ENXIO   an INQ has been detected to be attached to the open file
#:            description of the request although INQs are not implemented
#:
CT2_IOC_ACKINT = (
    _IOR(CT2_IOC_MAGIC, 10, ctypes.sizeof(ctypes.POINTER(ct2_in))),
    "CT2_IOC_ACKINT",
    __CT2_ERRORS("acknowledge interrupt"),
)


#: CT2_IOC_AINQ - "[A]ttach [I]nterrupt [N]otification [Q]ueue"
#:
#: returns:
#:
#:    ENOSYS  not implemented
#:
CT2_IOC_AINQ = (
    _IOW(CT2_IOC_MAGIC, 11, CT2_SIZE),
    "CT2_IOC_AINQ",
    __CT2_ERRORS("attach INQ"),
)


#: CT2_IOC_DINQ - "[D]etach [I]nterrupt [N]otification [Q]ueue"
#:
#: returns:
#:
#:    ENOSYS  not implemented
#:
CT2_IOC_DINQ = _IO(CT2_IOC_MAGIC, 12), "CT2_IOC_DINQ", __CT2_ERRORS("detach INQ")


#: CT2_IOC_RINQ - "D[R]ain [I]nterrupt [N]otification [Q]ueue"
#:
#: returns:
#:
#:    ENOSYS  not implemented
#:
CT2_IOC_RINQ = (
    _IOR(CT2_IOC_MAGIC, 13, ctypes.sizeof(ctypes.POINTER(ct2_inv))),
    "CT2_IOC_RINQ",
    __CT2_ERRORS("drain INQ"),
)


#: CT2_IOC_FINQ - "[F]lush [I]nterrupt [N]otification [Q]ueue"
#:
#: returns:
#:
#:    ENOSYS  not implemented
#:
CT2_IOC_FINQ = (
    _IOR(CT2_IOC_MAGIC, 14, ctypes.sizeof(ctypes.POINTER(timespec))),
    "CT2_IOC_FINQ",
    __CT2_ERRORS("flush INQ"),
)


def i2bool(value, bit=0):
    return bool(value & (1 << bit))


def i2enum(value, enu, mask):
    return enu(value & mask)


def i2int(value, mask, shift=0):
    if shift < 0:
        return (value >> shift) & mask
    return (value << shift) & mask


def __build_type(name, fromint, toint=None, doc=None):
    def build(**kwargs):
        result = fromint(0)
        result.update(kwargs)
        return result

    build.__name__ = name
    build.__doct__ = doc
    build.fromint = fromint
    if toint:
        build.toint = toint
    return build


CtStatus = __build_type(
    "CtStatus",
    lambda v: dict(enable=i2bool(v, 0), run=i2bool(v, 16)),
    doc="Counter status (enabled and running)",
)


FilterInput = __build_type(
    "FilterInput",
    lambda v: dict(
        clock=i2enum(v, FilterClock, 0b111),
        selection=i2enum(v, FilterInputSelection, 0b11000),
    ),
    lambda d: d["clock"] | d["selection"],
    doc="Channel input filter (clock freq., selection)",
)


FilterOutput = __build_type(
    "FilterOutput",
    lambda v: dict(
        clock=i2enum(v, FilterClock, 0b111),
        enable=i2bool(v, 3),
        polarity_inverted=i2bool(v, 4),
    ),
    lambda d: d["clock"] | d["enable"] << 3 | d["polarity_inverted"] << 4,
    doc="Channel output filter (clock freq., enabled, polarity_inverted)",
)


AMCCFIFOStatus = __build_type(
    "AMCCFIFOStatus",
    lambda v: dict(
        read_empty=i2bool(v, 0),
        write_full=i2bool(v, 1),
        read_full=i2bool(v, 2),
        write_empty=i2bool(v, 3),
    ),
    doc="Card general status. Returned by :meth:`P201.get_general_status`",
)


FIFOStatus = __build_type(
    "FIFOStatus",
    lambda v: dict(
        size=i2int(v, 0x1FFF),
        overrun_error=i2bool(v, 16),
        read_error=i2bool(v, 17),
        write_error=i2bool(v, 18),
        empty=i2bool(v, 19),
        full=i2bool(v, 20),
    ),
    doc="FIFO status. Returned by :meth:`P201.get_FIFO_status`",
)


CtConfig = __build_type(
    "CtConfig",
    lambda v: dict(
        clock_source=i2enum(v, CtClockSrc, 0x7F),
        gate_source=i2enum(v, CtGateSrc, 0x1F80),
        hard_start_source=i2enum(v, CtHardStartSrc, 0xFE000),
        hard_stop_source=i2enum(v, CtHardStopSrc, 0x7F00000),
        reset_from_hard_soft_stop=i2bool(v, 30),
        stop_from_hard_stop=i2bool(v, 31),
    ),
    lambda d: d["clock_source"]
    | d["gate_source"]
    | d["hard_start_source"]
    | d["hard_stop_source"]
    | d["reset_from_hard_soft_stop"] << 30
    | d["stop_from_hard_stop"] << 31,
    doc="""Counter configuration
    clock_source
        Describes the source that triggers a counter event

    gate_source
        counter gate source

    hard_start_source
        Describes the event that triggers the counter to start

    hard_stop_source
        Describes the event that triggers the counter to stop

    reset_from_hard_soft_stop
        Set it to True to tell the counter to reset its value when a stop
        signal (hardware or software) is received. Set it to False to leave
        the counter value unchanged when a stop signal occurs

    stop from hard stop
        Set it to True to disable the counter when a hardware stop signal
        is received. Set to False to maintain the counter enabled even after a
        hardware stop signal is received.

    To be used with methods :meth:`P201.get_counter_config` and
    :meth:`P201.set_counter_config`""",
)


TriggerInterrupt = __build_type(
    "TriggerInterrupt",
    lambda v: dict(rising=i2bool(v, 0), falling=i2bool(v, 16)),
    lambda d: d["rising"] << 0 | d["falling"] << 16,
    doc="""Trigger interrupt information.

    To be used with methods :meth:`P201.get_channels_interrupts` and
    :meth:`P201.set_channels_interrupts`.

    Also the result of :meth:`P201.get_interrupts`.
    """,
)


class BaseCard:
    """
    CT2 card base class
    """

    #: list of valid card counters
    COUNTERS = ()

    #: list of valid card channels
    CHANNELS = ()

    #: list of valid card input channels
    INPUT_CHANNELS = ()

    #: list of valid card ouput channels
    OUTPUT_CHANNELS = ()

    #: fifo size (bytes)
    FIFO_SIZE = 0

    def __init__(self, interface=None):
        self.interface = CardInterface() if interface is None else interface
        self.__interrupt_buffer_size = 0
        self.__log = logging.getLogger(str(self))
        self.connect()

    def __str__(self):
        return "{0.__class__.__name__}({0.interface})".format(self)

    def __repr__(self):
        return str(self)

    @property
    def fifo(self):
        try:
            return self.__fifo_mmap
        except AttributeError:
            self.__fifo_mmap = self.__create_fifo_mmap()
        return self.__fifo_mmap

    def __create_fifo_mmap(self, length=None):
        # remember: need exclusive access to use FIFO
        if not self.has_exclusive_access():
            self.request_exclusive_access()
        dev_stat = os.fstat(self.fileno())
        # print("%d:%d" % (os.major(dev_stat.st_rdev), os.minor(dev_stat.st_rdev)))
        if not stat.S_ISCHR(dev_stat.st_mode):
            raise CT2Exception(
                "Cannot memory map FIFO: file descriptor '%s' "
                "does not point to a special character file"
            )
        if length is None:
            length = self.FIFO_SIZE
        elif length > self.FIFO_SIZE:
            raise CT2Exception("FIFO size exceeds maximum of %d" % self.FIFO_SIZE)
        elif length % CT2_REG_SIZE:
            raise CT2Exception("FIFO size must be multiple of %d" % CT2_REG_SIZE)

        import mmap

        return mmap.mmap(
            self.fileno(),
            length,
            flags=mmap.MAP_PRIVATE,
            prot=mmap.PROT_READ,
            offset=CT2_MM_FIFO_OFF,
        )

    def connect(self):
        self.interface.connect()
        self.__exclusive = False

    def disconnect(self):
        self.interface.disconnect()
        self.__exclusive = False

    def fileno(self):
        """
        internal card file descriptor (don't use this member directly on your
        code)
        """
        return self.interface.fileno()

    def request_exclusive_access(self):
        """
        Request exclusive access to the card. Nothing happens if the card
        has already exclusive access.

        :raises CT2Exception: if fails to get exclusive access
        """
        self.interface.ioctl(CT2_IOC_QXA)
        self.__exclusive = True

    def relinquish_exclusive_access(self):
        """
        Relinquish exclusive access. Always succeeds.
        """
        self.interface.ioctl(CT2_IOC_LXA)
        self.__exclusive = False

    def has_exclusive_access(self):
        """
        Returns True if this card object has exclusive access or False otherwise

        :return: True if this card object has exclusive access or False otherwise
        :rtype: bool
        """
        return self.__exclusive

    def reset(self):
        """
        Resets the card.

        :raises CT2Exception: if fails to reset the card
        """
        self.interface.ioctl(CT2_IOC_DEVRST)

    def __enable_interrupts(self, fifo_size):
        """
        Enables driver IRQ handler with the given number of FIFO entries

        :param fifo_size: FIFO depth (number of FIFO entries)
        :type fifo_size: int

        :raises CT2Exception: if fails to enable interrupts
        """
        self.interface.ioctl(CT2_IOC_EDINT, fifo_size)

    def __disable_interrupts(self):
        """
        Disables the driver IRQ handler
        """
        self.interface.ioctl(CT2_IOC_DDINT)

    def __source_irq_reg_name(self, reg):
        return "SOURCE_IT_" + reg

    def __read_source_irq_reg(self, reg):
        """
        Reads the source IRQ register
        """
        return self.read_reg(self.__source_irq_reg_name(reg))

    def __write_source_irq_reg(self, reg, val):
        """
        Writes on source IRQ register and enable/disable IRQ handler
        """
        # Ensure that the kernel will handle IRQs before enabling ...
        if val:
            self.__enable_interrupts(self.__interrupt_buffer_size)
        self.write_reg(self.__source_irq_reg_name(reg), val)
        # Check if IRQ handler can be disabled
        if not val:
            other = "A" if reg == "B" else "B"
            if not self.__read_source_irq_reg(other):
                self.__disable_interrupts()

    def acknowledge_interrupt(self):
        """
        Acknowledge interrupt.

        The result is a tuple of 2 elements containing:

          * a tuple of 5 elements containing:

            * counters stop triggered interrupt (set)
            * channels rising and/or falling edge triggered interrupts (set)
            * DMA transfer interrupt enabled (bool)
            * FIFO half full interrupt enabled (bool)
            * FIFO transfer error or too close DMA trigger enabled (bool)
          * time stamp (seconds)

        Active elements mean that *at least* one such notification was
        delivered. If no new interrupt notification occurred since last call
        the time stamp contains the time the value of the value of the
        interrupt status in the interrupt notification storage was last read.
        Otherwise, the time stamp corresponds to the the time the interrupt
        status was last updated is saved.

        :return:
            counters, channels, DMA, FIFO and error interrupt information plus
            time stamp
        :rtype:
            tuple( tuple(set<int>, set<int>, bool, bool, bool), float )
        """
        data = ct2_in()
        self.interface.ioctl(CT2_IOC_ACKINT, data, True)
        t = data.stamp.tv_sec + data.stamp.tv_nsec * 1E-9
        return self.__decode_ctrl_it(data.ctrl_it), t

    def read_reg(self, register_name):
        """
        Read from the specified register and return a 32bit integer

        **Low level call**.

        :param register_name: name of the register (case insensitive)
        :type register_name: str
        :return: the content of the register. Interpret as a 32bit unsigned integer
        :rtype: int

        :raises OSError: in case the operation fails
        """
        register_name = register_name.upper()
        offset = CT2_R_DICT[register_name][0]
        iresult = self.interface.read_offset(offset)
        self.__log.debug(
            " read %020s (addr=%06s) = %010s", register_name, hex(offset), hex(iresult)
        )
        return iresult

    def write_reg(self, register_name, ivalue):
        """
        Write from the specified register a given integer value. The value is
        interpreted as a 32bit unsigned integer

        **Low level call**.

        :param register_name: name of the register (case insensitive)
        :type register_name: str
        :param ivalue: value to write
        :type ivalue: int

        :raises OSError: in case the operation fails
        """
        register_name = register_name.upper()
        offset = CT2_R_DICT[register_name][0]
        self.__log.debug(
            "write %020s (addr=%06s, value=%010s)",
            register_name,
            hex(offset),
            hex(ivalue),
        )
        return self.interface.write_offset(offset, ivalue)

    def calc_fifo_events(self, fifo_status, nb_counters=None):
        if nb_counters is None:
            etl = self.get_DMA_enable_trigger_latch()
            nb_counters = list(etl[1].values()).count(True)
        data_len = min(fifo_status["size"], self.FIFO_SIZE / CT2_REG_SIZE)
        return data_len / nb_counters, nb_counters

    def read_fifo(self, fifo_status, nb_events=0, use_mmap=False):
        max_events, nb_counters = self.calc_fifo_events(fifo_status)
        if not nb_events or nb_events > max_events:
            nb_events = max_events
        if nb_events == 0:
            return None, fifo_status
        read_len = nb_events * nb_counters * CT2_REG_SIZE
        if use_mmap:
            buff = self.fifo[:read_len]
        else:
            fifo_offset = CT2_RW_FIFO_OFF * CT2_REG_SIZE
            buff = self.interface.pread(fifo_offset, n=read_len)

        return (
            numpy.ndarray((nb_events, nb_counters), dtype=numpy.uint32, buffer=buff),
            fifo_status,
        )

    def software_reset(self):
        """
        Does a software reset on the card.

        :raises OSError: in case the operation fails
        """
        self.write_reg("COM_GENE", 1 << 7)

    def get_general_status(self):
        """
        Returns the general card status as a tuple of two elements:
        - card id (int)
        - AMCC fifo status (:class:`AMCCFIFOStatus`)

        :return: the general card status
        :rtype: tuple<int, :class:`AMCCFIFOStatus`>
        """
        result = self.read_reg("CTRL_GENE")
        card_id = (result & CT2_CTRL_GENE_CARDN_MSK) >> CT2_CTRL_GENE_CARDN_OFF
        return card_id, AMCCFIFOStatus.fromint(result)

    def get_output_channels_level(self):
        """
        Returns the NIM/TTL level of all output channels (9 and 10)

        :return: the NIM/TTL level of all output channels (9 and 10)
        :rtype: dict<int: :class:`Level`>

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("NIVEAU_OUT")
        result, mask = {}, ((1 << 8) | (1 << 24))
        for i, channel in enumerate(self.OUTPUT_CHANNELS):
            level = Level.DISABLE
            reg = (register >> i) & mask
            TTL, NIM = reg & (1 << 8), reg & (1 << 24)
            if TTL:
                if NIM:
                    level = Level.AUTO
                else:
                    level = Level.TTL
            else:
                if NIM:
                    level = Level.NIM
                else:
                    level = Level.DISABLE

            result[channel] = level
        return result

    def set_output_channels_level(self, output_level):
        """
        Sets output channels level (disable, TTL or NIM)

        .. warning::
            non specified output channels will have their level set to disable

        :param output_level:
            dictionary where keys are output channel numbers and value is
            an instance of :class:`Level` representing the channel level
        :type output_level: dict<int: :class:`Level`>

        :raises OSError: in case the operation fails
        """
        register = 0
        for i, channel in enumerate(self.OUTPUT_CHANNELS):
            level = output_level.get(channel, Level.DISABLE)
            if level == Level.AUTO:
                raise ValueError(
                    "Invalid level for output channel %d: "
                    "output channels cannot have AUTO level" % channel
                )
            elif level == Level.TTL:
                register |= (1 << 8) << i
            elif level == Level.NIM:
                register |= (1 << 24) << i
            else:
                pass
        self.write_reg("NIVEAU_OUT", register)

    def get_input_channels_level(self):
        """
        Returns the NIM/TTL input level of all channels

        :return: the NIM/TTL input level of all channels
        :rtype: dict<int: :class:`Level`>

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("NIVEAU_IN")
        result, mask = {}, ((1 << 0) | (1 << 16))
        for i, channel in enumerate(self.CHANNELS):
            level = Level.DISABLE
            TTL = register & (1 << i)
            NIM = register & (1 << 16 << i)
            if TTL:
                if NIM:
                    level = Level.AUTO
                else:
                    level = Level.TTL
            else:
                if NIM:
                    level = Level.NIM
                else:
                    level = Level.DISABLE

            result[channel] = level
        return result

    def set_input_channels_level(self, input_level):
        register = 0
        for i, channel in enumerate(self.CHANNELS):
            level = input_level.get(channel, Level.DISABLE)
            if level == Level.AUTO:
                register |= (1 << i) | (1 << 16 << i)
            elif level == Level.TTL:
                register |= 1 << i
            elif level == Level.NIM:
                register |= 1 << 16 << i
            else:
                pass
        self.write_reg("NIVEAU_IN", register)

    def get_output_channels_software_enable(self):
        """
        Returns the ouput channels levels as a dictionary with keys
        being channel numbers (starting in 1) and an integer (0 or 1)
        representing the channel output level

        :return: the ouput channels levels
        :rtype: dict<int: int>

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("SOFT_OUT")
        result = {}
        for channel in self.OUTPUT_CHANNELS:
            result[channel] = register & (1 << (channel - 1)) != 0 and 1 or 0
        return result

    def set_output_channels_software_enable(self, channels_output_level):
        """
        Sets the cards output channels level.

        .. warning::
            non specified output channels will have their level reset to 0

        :param channels_output_level:
            dictionary where key is the output channel numbers and value is
            either 0 or 1 representing the channel ouput level
        :type channels_output_level: dict<int: int>

        :raises OSError: in case the operation fails
        """
        register = 0
        for channel in self.OUTPUT_CHANNELS:
            if channels_output_level.get(channel, 0):
                register |= 1 << (channel - 1)
        self.write_reg("SOFT_OUT", register)

    def get_output_channels_source(self):
        """
        Returns the current output channels source configuration

        :return:
            dictionary where key is the output channel number and value is the
            output channel source (instance of :class:`OutputSrc`)
        :rtype: dict<int: class:`OutputSrc>`
        """
        result = {}
        register = self.read_reg("SEL_SOURCE_OUTPUT")
        for n, channel in enumerate(self.OUTPUT_CHANNELS):
            result[channel] = OutputSrc((register >> (n * 8)) & 0xFF)
        return result

    def set_output_channels_source(self, output_src):
        """
        Sets the cards ouput channels source configuration

        :param output_src:
            dictionary where key is the output channel number and value is the
            ouput channel source (instance of :class:`OutputSrc`)
        :type ouput_src: dict<int: class:`OutputSrc>`
        """
        register = 0
        for n, channel in enumerate(self.OUTPUT_CHANNELS):
            src = output_src.get(channel, OutputSrc.DISABLE)
            register |= src.value << (n * 8)
        self.write_reg("SEL_SOURCE_OUTPUT", register)

    def get_output_channels_filter(self):
        """
        Returns the current output channels filter configuration and polarity
        selection

        :return:
            dictionary where key is the output channel number and value is the
            filter and polarity configuration (instance of
            :class:`FilterOutput`)
        :rtype: dict<int: class:`FilterOutput>`
        """
        result = {}
        register = self.read_reg("SEL_FILTRE_OUTPUT")
        for n, channel in enumerate(self.OUTPUT_CHANNELS):
            result[channel] = FilterOutput.fromint((register >> (n * 8)) & 0xFF)
        return result

    def set_output_channels_filter(self, filter):
        """
        Sets the given ouput channels filter configuration and polarity
        selection

        :param filter:
            dictionary where key is the channel number and value is the filter
            and polarity configuration (instance of :class:`FilterOutput`)
        :type filter: dict<int: class:`FilterOutput>`
        """
        register = 0
        for n, channel in enumerate(self.OUTPUT_CHANNELS):
            try:
                register |= FilterOutput.toint(filter[channel]) << (n * 8)
            except KeyError:
                pass
        self.write_reg("SEL_FILTRE_OUTPUT", register)

    def get_input_channels_filter(self):
        """
        Returns the filter configuration and deglitcher enable for all input
        channels

        :return:
            dictionary where key is the input channel number and value is the
            filter configuration (instance of :class:`FilterInput`)
        :rtype: dict<int: class:`FilterInput>`
        """
        result = {}
        reg_a = self.read_reg("SEL_FILTRE_INPUT_A")
        reg_b = self.read_reg("SEL_FILTRE_INPUT_B")
        for n, channel in enumerate(self.INPUT_CHANNELS):
            if channel < 7:
                value = (reg_a >> (n * 5)) & 0b11111
            else:
                value = (reg_b >> ((n - 6) * 5)) & 0b11111
            result[channel] = FilterInput.fromint(value)
        return result

    def set_input_channels_filter(self, filter):
        reg_a, reg_b = 0, 0
        for n, channel in enumerate(self.INPUT_CHANNELS):
            try:
                if channel < 7:
                    reg_a |= FilterInput.toint(filter[channel]) << (n * 5)
                else:
                    reg_b |= FilterInput.toint(filter[channel]) << ((n - 6) * 5)
            except KeyError:
                pass
        self.write_reg("SEL_FILTRE_INPUT_A", reg_a)
        self.write_reg("SEL_FILTRE_INPUT_B", reg_b)

    def get_DMA_enable_trigger_latch(self):
        """
        Returns DMA enable and trigger source and FIFO store configuration

        :return:
            a tuple of two dictionaries. The first describes which counter
            latch signals trigger DMA. The second describes which counter
            latches are stored to FIFO when DMA is triggered
        :rtype: tuple (dict<int: bool>, dict<int: bool>)
        """
        register = self.read_reg("CMD_DMA")
        counters, latches = {}, {}
        for n, counter in enumerate(self.COUNTERS):
            counters[counter] = (register & (1 << n)) != 0
            latches[counter] = (register & (1 << n << 16)) != 0
        return counters, latches

    def set_DMA_enable_trigger_latch(
        self, counters=None, latches=None, reset_fifo_error_flags=False
    ):
        """
        Configures the DMA trigger sources and FIFO store.

        :param counters:
            a container of counters for which the latch transfer will trigger
            DMA (can be any python container (tuple, list, set, iterator,
            even dict. If a dictionary is given, the boolean value of each key
            will determine if enable or disable the corresponding counter latch
            trigger))
        :type counters: container (tuple, list, set, iterator, even dict.)
        :param latches:
            a container of counters latches which will be stored to FIFO on
            a DMA trigger (can be any python container (tuple, list, set,
            iterator, even dict. If a dictionary is given, the boolean value of
            each key will determine if enable or disable the corresponding
            counter latch trigger)
        :type latches: container (tuple, list, set, iterator, even dict.)

        :param reset_fifo_error_flags:
            set to True to reset FIFO and error flags. Usually not used.
            Exists for convenience of implementation since it is in the same
            register as the rest of the DMA configuration
        :type reset_fifo_error_flags: bool
        """
        if counters is None:
            counters = ()
        elif isinstance(counters, dict):
            counters = [c for c, yesno in list(counters.items()) if yesno]
        if latches is None:
            latches = ()
        elif isinstance(latches, dict):
            latches = [l for l, yesno in list(latches.items()) if yesno]

        register = 0
        for counter in counters:
            register |= 1 << (counter - 1)
        for latch in latches:
            register |= 1 << (latch - 1) << 16
        if not reset_fifo_error_flags:
            register |= 1 << 31
        self.write_reg("CMD_DMA", register)

    def reset_FIFO_error_flags(self):
        """
        Resets FIFO error flags
        """
        self.set_DMA_enable_trigger_latch(
            *self.get_DMA_enable_trigger_latch(), reset_fifo_error_flags=True
        )

    def get_FIFO_status(self):
        """
        Returns the current FIFO status

        :return: the card's current FIFO status
        :rtype: class:`FIFOStatus`
        """
        register = self.read_reg("CTRL_FIFO_DMA")
        return FIFOStatus.fromint(register)

    def get_channels_interrupts(self):
        """
        Returns the channels interrupt configuration

        :return:
            a dictionary where keys are channels (starting a 1) and value
            is an instance of :class:`TriggerInterrupt`
        :rtype: dict<int: :class:`TriggerInterrupt`>
        """
        result = {}
        register = self.__read_source_irq_reg("A")
        mask = (1 << 0) | (1 << 16)
        for channel in self.CHANNELS:
            reg = (register >> (channel - 1)) & mask
            result[channel] = TriggerInterrupt.fromint(reg)
        return result

    def set_channels_interrupts(self, channels_triggers=None):
        """
        Sets the channels interrupt selectors.

        :param channels_triggers:
            a dictionary are keys are channels (starting at 1) and value
            is an instance of :class:`TriggerInterrupt` describing which
            edge (rising, falling, both or none) will trigger the channel
            interrupt
        :type channles_triggers: dict<int: :class:`TriggerInterrupt`>
        """
        if channels_triggers is None:
            channels_triggers = {}
        register = 0
        for channel, triggers in list(channels_triggers.items()):
            register |= TriggerInterrupt.toint(triggers) << (channel - 1)
        self.__write_source_irq_reg("A", register)

    def __get_source_it_b(self):
        counters = {}
        register = self.__read_source_irq_reg("B")
        for counter in self.COUNTERS:
            counters[counter] = (register & 1 << (counter - 1)) != 0
        dma = (register & (1 << 12)) != 0
        fifo_half_full = (register & (1 << 13)) != 0
        error = (register & (1 << 14)) != 0
        return counters, dma, fifo_half_full, error

    def __set_source_it_b(
        self, counters=None, dma=False, fifo_half_full=False, error=False
    ):
        if counters is None:
            counters = ()
        elif isinstance(counters, dict):
            counters = [c for c, trigger in list(counters.items()) if trigger]

        register = 0
        for counter in counters:
            register |= 1 << (counter - 1)
        register |= (1 << 12) if dma else 0
        register |= (1 << 13) if fifo_half_full else 0
        register |= (1 << 14) if error else 0
        self.__write_source_irq_reg("B", register)

    def get_counters_interrupts(self):
        """
        Returns the counters interrupt configuration

        dict<int: bool>
        key: counter
        value: True if stop triggered interrupt or False otherwise
        """
        return self.__get_source_it_b()[0]

    def set_counters_interrupts(self, counters=None):
        """
        Sets the counter source interrupt configuration

        .. note::
            *techincal note*.This call leaves DMA and FIFO interrupt
            parameters unchanged (even though they come in the same
            register as the counter interrupts)

        dict<int: bool>
        key: counter
        value: True if stop triggered interrupt or False otherwise
        """
        # First, make sure we leave bits 12, 13 and 14 unchanged
        # (these correspond to DMA, FIFO and error interrupts)
        dma, fifo_half_full, error = self.get_DMA_FIFO_error_interrupts()
        self.__set_source_it_b(counters, dma, fifo_half_full, error)

    def get_DMA_FIFO_error_interrupts(self):
        """
        Returns the interrupt configuration for the following possible
        interruptions:

            - End of DMA transfer
            - FIFO half full
            - FIFO transfer error or too close DMA triggers error

        :return:
            a tuple of three booleans representing: DMA transfer interrupt
            enabled, FIFO half full interrupt enabled and FIFO transfer error
            or too close DMA trigger enabled
        :rtype: tuple(bool, bool, bool)
        """
        return self.__get_source_it_b()[1:]

    def set_DMA_FIFO_interrupts(self, dma=False, fifo_half_full=False, error=False):
        """
        Sets the interrupt configuration for the following possible
        interruptions:

            - End of DMA transfer
            - FIFO half full
            - FIFO transfer error or too close DMA triggers error

        :param dma:
            set to True to enable interrupt on end of DMA transfer
            [default: False]
        :type dma: bool
        :param fifo_half_full:
            set to True to enable interrupt on FIFO half full
            [default: False]
        :type fifo_half_full: bool
        :param error:
            set to True to enable interrupt on FIFO transfer error
            or too close DMA triggers error [default: False]
        :type eror: bool
        """
        # First, make sure we leave bits 0 to 11 unchanged
        # (these correspond to counter stop trigerred interrupts)
        counters = self.get_counters_interrupts()
        self.__set_source_it_b(counters, dma, fifo_half_full, error)

    def get_interrupts(self):
        """
        A convenience method to get all interrupt configuration

        The result is a tuple of 5 elements containing:

            * counters stop triggered interrupt (dict<int: bool>)
            * channels rising and/or falling edge triggered interrupts
              (dict<int: class:`TriggerInterrupt`)
            * DMA transfer interrupt enabled (bool)
            * FIFO half full interrupt enabled (bool)
            * FIFO transfer error or too close DMA trigger enabled (bool)

        :return: channels, counters, DMA, FIFO and error interrupt information
        :rtype: tuple(dict<int: class:`TriggerInterrupt`>, dict<int: bool>, bool, bool, bool)
        """
        channels = self.get_channels_interrupts()
        counters, dma, fifo_half_full, error = self.__get_source_it_b()
        return channels, counters, dma, fifo_half_full, error

    def set_interrupts(
        self, channels=None, counters=None, dma=False, fifo_half_full=False, error=False
    ):
        """
        A convenience method to configure interrupts
        """
        self.set_channels_interrupts(channels)
        self.__set_source_it_b(counters, dma, fifo_half_full, error)

    def __decode_ctrl_it(self, register):
        counters, channels = set(), set()
        for channel in self.CHANNELS:
            if (register & (1 << (channel - 1))) != 0:
                channels.add(channel)
        for counter in self.COUNTERS:
            if (register & ((1 << (counter - 1)) << 12)) != 0:
                counters.add(counter)
        dma = (register & (1 << 25)) != 0
        fifo_half_full = (register & (1 << 26)) != 0
        error = (register & (1 << 27)) != 0
        return counters, channels, dma, fifo_half_full, error

    def get_interrupts_status(self):
        """
        Returns the interrupt status

        .. warning::
            Reading out interrupt resets it and disables further interrupt.

        """
        register = self.read_reg("CTRL_IT")
        return self.__decode_ctrl_it(register)

    def get_channels_readback(self):
        """
        Returns input and output channels readback after TTL or NIM has been selected

        :return:
            a tuple of two items:
                * dict where key is input channel number and value is True if readback or False otherwise
                * dict where key is output channel number and value is True if readback or False otherwise
        :rtype: tuple(dict<int: bool>, dict<int: bool>)
        """
        register = self.read_reg("RD_IN_OUT")
        in_result, out_result = {}, {}
        for i, channel in enumerate(self.CHANNELS):
            in_result[channel] = (register & (1 << (i))) != 0
        for i, channel in enumerate(self.OUTPUT_CHANNELS):
            out_result[channel] = (register & (1 << (i + 24))) != 0
        return in_result, out_result

    def get_clock(self):
        """
        Returns the global clock frequency

        :return: the global clock frequency
        :rtype: :class:`Clock`

        :raises OSError: in case the operation fails
        """
        result = self.read_reg("COM_GENE")
        if not (result & CT2_COM_GENE_ENAB_MSK):
            return Clock.CLK_DISABLE
        # silly: there are two possible values for 60 MHz
        if result == 0xb11011:
            result = 0xb11010
        return Clock(result)

    def set_clock(self, clock):
        """
        Sets the global card clock

        To disable the clock use :attr:`Clock.CLK_DISABLE`

        :param clock: new clock frequency
        :type clock: :class:`Clock`

        :raises OSError: in case the operation fails
        """
        self.write_reg("COM_GENE", clock.value)

    def get_counters_status(self):
        """
        Returns the card's counter status

        :return: the counters status
        :rtype: dict<int: :class:`CtsStatus`>

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("RD_CTRL_CMPT")
        result, mask = {}, (1 << 0) | (1 << 16)
        for i, c in enumerate(self.COUNTERS):
            reg = (register >> i) & mask
            result[c] = CtStatus.fromint(reg)
        return result

    def get_counter_value(self, counter):
        """
        Returns the current value of the given counter

        :param counter: counter number (starts with 1)
        :type counter: int
        :return: counter value
        :rtype: int

        :raises OSError: in case the operation fails
        """
        offset = CT2_R_DICT["RD_CMPT_1"][0] + (counter - 1) * CT2_REG_SIZE
        return self.interface.read_offset(offset)

    def get_counters_values(self):
        offset = CT2_R_DICT["RD_CMPT_1"][0]
        return self.interface.read_offset_array(offset, len(self.COUNTERS))

    def get_latch_value(self, latch):
        """
        Returns the current value of the given latch

        :param latch: latch number (starts with 1)
        :type latch: int
        :return: latch value
        :rtype: int

        :raises OSError: in case the operation fails
        """
        offset = CT2_R_DICT["RD_LATCH_CMPT_1"][0] + (latch - 1) * CT2_REG_SIZE
        return self.interface.read_offset(offset)

    def get_latches_values(self):
        offset = CT2_R_DICT["RD_LATCH_CMPT_1"][0]
        return self.interface.read_offset_array(offset, len(self.COUNTERS))

    def set_test_reg(self, value):
        """
        Writes the given value to the test register
        :param value: the new value
        :type value: int

        :raises OSError: in case the operation fails
        """
        self.write_reg("TEST_REG", value)

    def get_test_reg(self):
        """
        Read the test register value

        :return: the test register value
        :rtype: int

        :raises OSError: in case the operation fails
        """
        return self.read_reg("TEST_REG")

    def get_counter_config(self, counter):
        """
        Returns the current configuration for the specified counter

        Example::

            >>> from bliss.controllers import ct2
            >>> p201 = ct2.P201()
            >>> print p201.get_counter_config()
            CtConfig(clock_source=CtClockSrc.CLK_100_MHz,
                     gate_source=CtGateSrc.GATE_CMPT,
                     hard_start_source=CtHardStartSrc.SOFTWARE,
                     hard_stop_source=CtHardStopSrc.SOFTWARE,
                     reset_from_hard_soft_stop=True,
                     stop_from_hard_stop=True)

        :param counter: counter number (starts with 1)
        :type counter: int
        :return: the current configuration for the specified counter
        :rtype: :class:`CtConfig`

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("CONF_CMPT_{0}".format(counter))
        return CtConfig.fromint(register)

    def set_counter_config(self, counter, config):
        """
        Sets the current configuration for the specified counter

        *config* parameter can be an instance of :class:`CtConfig` or
        an integer representing the direct bit counter configuration.

        Example::

            from bliss.controllers.ct2 import P201, CtConfig

            config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                              gate_source=CtGateSrc.GATE_CMPT,
                              hard_start_source=CtHardStartSrc.SOFTWARE,
                              hard_stop_source=CtHardStopSrc.CT_10_EQ_CMP_10,
                              reset_from_hard_soft_stop=True,
                              stop_from_hard_stop=True)

            p201 = P201()
            p201.set_counter_config(10, config)

        :param counter: counter number (starts with 1)
        :type counter: int
        :param config: counter configuration
        :type config: :class:`CtConfig`, int

        :raises OSError: in case the operation fails
        """
        config = CtConfig.toint(config)
        self.write_reg("CONF_CMPT_{0}".format(counter), config)

    def set_counters_config(self, counters_cfg):
        """
        Sets the configuration for the given counters.

        .. seealso:: :meth:`.set_counter_config`

        :param counters_cfg:
            a dictionary where keys are counters (starting with 1) and value is
            the corresponding counter configuration (instance of
            :class:`CtConfig`)
        :type counters_cfg: dict<int: :class:`CtConfig`>
        """
        for counter, config in list(counters_cfg.items()):
            self.set_counter_config(counter, config)

    def get_latch_sources(self, latch):
        """
        Returns the 2 counters latch sources for the given latch

        Example: for latch "C" it will give counter sources of counters 5, 6

        This is considered a *low level call* since it assumes knowledge
        of the internal card register configuration.
        For simpler interface use :meth:`~P201.get_counter_latch_sources`

        :param latch: latch name (A, B, ..., F) (case insensitive)
        :type: str

        :return:
            a dictionary where keys are counters (starting with 1) and value is
            a set of integers representing the counter(s) signals which
            will trigger a latch on the corresponding counter key.
        :rtype: dict<int: set<int>>

        :raises OSError: in case the operation fails
        """
        latch = latch.upper()
        latch_nb = ord(latch) - ord("A") + 1
        c1, c2 = 2 * latch_nb - 1, 2 * latch_nb

        register = self.read_reg("SEL_LATCH_" + latch)

        result = {c1: set(), c2: set()}
        for bit_nb, bit in enumerate(bin(register)[-1:1:-1], 1):
            if bit == "0":
                continue
            if bit_nb <= 12:
                counter, c = bit_nb, c1
            else:
                counter, c = bit_nb - 16, c2
            counters = result[c]
            counters.add(counter)
        return result

    def set_latch_sources(self, latch, counter_sources):
        """
        Sets the latch source of signals HARD_STOP, SOFT_STOP, SOFT_DISABLE for
        the 2 counters corresponding to the given latch

        counters in *counter_sources* that don't belong to the given latch
        are ignored

        .. warning::
            relevant counter(s) which are missing from counter_sources
            will be set as non latched.
            For a non intrusive call consider using
            :meth:`~P201.set_counter_latch_sources` instead

        This is considered a *low level call* since it assumes knowledge
        of the internal card register configuration.
        For simpler interface use :meth:`~P201.set_counter_latch_sources`

        :param latch: latch name (A, B, ..., F) (case insensitive)
        :type: str
        :param counter_sources:
            a dictionary where keys are counters (starting with 1) and value is
            either a single integer or an iterator of integers representing the
            counter(s) signals which will trigger a latch on the corresponding
            counter key. The iterator can any python container (set,list, tuple,
            even dict where keys are counter numbers)
        :type counter_sources: dict<int: int|iterator>

        :return: integer representing the bits written into given latch register
        :rtype: int

        :raises OSError: in case the operation fails
        """
        latch = latch.upper()
        latch_nb = ord(latch) - ord("A") + 1
        c1, c2 = 2 * latch_nb - 1, 2 * latch_nb

        s1, s2 = counter_sources.get(c1, ()), counter_sources.get(c2, ())
        if isinstance(s1, int):
            s1 = (s1,)
        if isinstance(s2, int):
            s2 = (s2,)

        # convert from list of counters to register bits
        source_bits = 0
        for sources, shift in ((s1, 0), (s2, 16)):
            sb = 0
            for source in sources:
                sb |= 1 << (source - 1)
            source_bits |= sb << shift

        self.write_reg("SEL_LATCH_" + latch, source_bits)
        return source_bits

    def add_latch_sources(self, latch, counter_sources):
        """*not implemented*"""
        raise NotImplementedError

    def get_counter_latch_sources(self, counter):
        """
        Returns the latch source configuration for the given counter

        :return:
            a set of integers representing the counter(s) signals which
            will trigger a latch on the given counter.
        :rtype: container

        :raises OSError: in case the operation fails
        """
        # even counter will be represented in high 16 bits part
        shift = (counter % 2 == 0) and 16 or 0

        # calculate which latch (A, B, ... F)
        latch_str = "SEL_LATCH_" + (chr(((counter - 1) % 12) // 2 + ord("A")))

        reg = (self.read_reg(latch_str) >> shift) & 0x0000FFFF

        return [ct for ct, bit in enumerate(bin(reg)[-1:1:-1], 1) if bit == "1"]

    def set_counter_latch_sources(self, counter, counter_sources):
        """
        Sets the latch source of signals HARD_STOP, SOFT_STOP, SOFT_DISABLE for
        the given counter.

        All other counters latch source configuration is left unchanged

        The following example will set counter 10 latch sources to be counters
        1, 2, 3 and 4. It will leave the latch source configuration off all
        other counters (including counter 9 - the latch "D" pair of counter 10)
        unchanged::

            p201.set_counter_latch_sources(10, (1, 2, 3, 4))

        :param counter: counter number (starts with 1)
        :type counter: int
        :param counter_sources:
            an iterator of integers representing the counter(s) signals which
            will trigger a latch on the corresponding counter key. It can be
            any python container (set,list, tuple, even dict where keys are
            counter numbers)
        :type counter_sources: container

        :raises OSError: in case the operation fails
        """
        if isinstance(counter_sources, int):
            counter_sources = (counter_sources,)

        # calculate which latch (A, B, ... F)
        latch_str = "SEL_LATCH_" + (chr(((counter - 1) % 12) // 2 + ord("A")))

        # even counter will be represented in high 16 bits part
        if counter % 2:
            shift = 0
            mask = 0xFFFF0000
        else:
            shift = 16
            mask = 0x0000FFFF

        # read register so it can be *ored* with the new counter setting
        # because each register contains info about two counters.
        # (Example: SEL_LATCH_B contains config of counters 3 and 4
        sibling_source_bits = self.read_reg(latch_str) | mask

        # convert from list of counters to register bits
        source_bits = 0
        for source in counter_sources:
            source_bits |= 1 << (source - 1)
        source_bits = (source_bits << shift) | sibling_source_bits

        self.write_reg(latch_str, source_bits)

    def set_counters_latch_sources(self, counter_sources):
        """
        Sets the latch source of signals HARD_STOP, SOFT_STOP, SOFT_DISABLE for
        all counters.

        Each counter can be latched by one or more sources. Sources are
        counters from 1 to 12.

        .. warning::
            All non specified counters will be set as non latched

        The following example will latch:

            - counter 1 on signals from counter 10
            - counter 2 on signals from counters 3, 4 and 5
            - counters 3 to 12 disable latch source

        ::

            p201.set_counters_latch_sources({1 : 10,
                                             2 : (3, 4, 5)})

        :param counter_sources:
            a dictionary where keys are counters (starting with 1) and value is
            either a single integer or an iterator of integers representing the
            counter(s) signals which will trigger a latch on the corresponding
            counter key. The iterator can any python container (set,list, tuple,
            even dict where keys are counter numbers)
        :type counter_sources: dict<int: int|iterator>

        :raises OSError: in case the operation fails
        """
        latches = {}
        for latch in "ABCDEF":
            latches[latch] = self.set_latch_sources(latch, counter_sources)
        return latches

        # initialize map of latches
        latches = {}
        for latch in "ABCDEF":
            latches[latch] = 0

        for counter, sources in list(counter_sources.items()):
            if isinstance(sources, int):
                sources = (sources,)
            source_bits = 0
            for source in sources:
                source_bits |= 1 << (source - 1)

            # even counter will be represented in high 16 bits part
            shift = (counter % 2 == 0) and 16 or 0
            source_bits = source_bits << shift

            # calculate which latch (A, B, ... F)
            latch = chr(((counter - 1) % 12) // 2 + ord("A"))
            register = latches[latch]
            latches[latch] = register | source_bits
        for latch, value in list(latches.items()):
            self.write_reg("SEL_LATCH_" + latch, value)
        return latches

    def get_counters_latch_sources(self):
        """
        Returns the latch source configuration for all counters

        :return:
            a dictionary where keys are counters (starting with 1) and value is
            a set of integers representing the counter(s) signals which
            will trigger a latch on the corresponding counter key.
        :rtype: dict<int: set<int>>

        :raises OSError: in case the operation fails
        """
        result = {}
        for latch in "ABCDEF":
            result.update(self.get_latch_sources(latch))
        return result

        # initialize map of sources
        result = {}
        for c in range(1, 13):
            result[c] = set()

        for latch in range(1, 7):
            latch_str = "SEL_LATCH_" + chr((latch - 1) + ord("A"))
            register = self.read_reg(latch_str)
            c1, c2 = 2 * latch - 1, 2 * latch
            for counter, bit in enumerate(bin(register)[-1:1:-1], 1):
                if bit == "0":
                    continue
                if counter <= 12:
                    latch_counter = c1
                else:
                    counter = counter - 16
                    latch_counter = c2
                counters = result[latch_counter]
                counters.add(counter)
                result[latch_counter] = counters
        return result

    def get_counter_comparator_value(self, counter):
        """
        Returns the given counter comparator value

        :param counter: counter number (starting at 1)
        :type counter: int
        :return: comparator value
        :rtype: int
        """
        return self.read_reg("COMPARE_CMPT_%d" % counter)

    def get_counters_comparators_values(self):
        offset = CT2_R_DICT["COMPARE_CMPT_1"][0]
        return self.interface.read_offset_array(offset, len(self.COUNTERS))

    def set_counter_comparator_value(self, counter, value):
        """
        Sets the given counter comparator value

        :param counter: counter number (starting at 1)
        :type counter: int
        :param value: comparator value
        :type value: int
        """
        self.write_reg("COMPARE_CMPT_%d" % counter, value)

    def set_counters_comparators_values(self, counters):
        for ct, value in list(counters.items()):
            self.set_counter_comparator_value(ct, value)

    def get_input_channels_50ohm_adapter(self):
        """
        Returns the enable/disable status of the input channel 50 ohm adapter

        :return:
            a dictionary where key is the input channel number (starting at 1)
            and value is bool (set to True if 50 ohm load is to be enabled,
            or False if it is to be disabled)
        :rtype: dict<int: bool>

        :raises OSError: in case the operation fails
        """
        result = {}
        for c in range(1, 10):
            result[c] = True

        register = self.read_reg("ADAPT_50") & P201_ADAPT_50_UMSK
        for input, bit in enumerate(bin(register)[-1:1:-1], 1):
            result[input] = bit == "0"
        return result

    def set_input_channels_50ohm_adapter(self, inputs):
        """
        Enable/disable 50 ohm input adapter from all input channels.

        .. warning::
           non specified channels will be set as 50 ohm disabled

        :param inputs:
            a container of integers representing input channel numbers (starting
            at 1). If a dictionary is given, the boolean value of each key will
            determine if enable or disable 50 ohm adapter)

        :raises OSError: in case the operation fails
        """
        register = 0
        if not isinstance(inputs, dict):
            inputs = dict([(c, True) for c in inputs])

        for channel in self.INPUT_CHANNELS:
            value = inputs.get(channel, False)
            if not value:
                register |= 1 << (channel - 1)
        self.write_reg("ADAPT_50", register)

    def start_counters_software(self, counters):
        """
        Trigger a software start on the given counters

        .. note::
            counters which are not given are not started

        :param counters:
            container of counters (starting at 1). It can be any python
            container of integers (tuple, list, set, iterable, even dict)
        """
        ct = {}
        for counter in counters:
            ct[counter] = True
        self.set_counters_software_start_stop(ct)

    def stop_counters_software(self, counters):
        """
        Trigger a software stop on the given counters

        .. note::
            counters which are not given are not stopped

        :param counters:
            container of counters (starting at 1). It can be any python
            container of integers (tuple, list, set, iterable, even dict)
        """
        ct = {}
        for counter in counters:
            ct[counter] = False
        self.set_counters_software_start_stop(ct)

    def set_counters_software_start_stop(self, counters):
        """
        Software starts or stops the given counters.

        .. note::
            counters which are not given are left unchanged

        :param counters:
            dictionary where key is the counter number (starting at 1)
            and value is bool (True means software start, False means software stop)
        :type counters: dict<int: bool>

        :raises OSError: in case the operation fails
        """
        register = 0
        for counter, action in list(counters.items()):
            reg = 1 << (counter - 1)
            if not action:
                reg = reg << 16
            register |= reg
        self.write_reg("SOFT_START_STOP", register)

    def trigger_counters_software_latch(self, counters):
        """
        Triggers a latch on the specified counters by software

        :param counters:
            container of counters (starting at 1). It can be any python
            container of integers (tuple, list, set, iterable, even dict)
        :type counters: container<int>
        """
        register = 0
        for c in counters:
            register |= 1 << (c - 1)
        self.write_reg("SOFT_LATCH", register)

    def set_counters_software_enable_disable(self, counters):
        """
        Software enables/disables specified counters

        .. note::
            counters which are not given are left unchanged

        :param counters:
            dictionary where key is the counter number (starting at 1)
            and value is bool (True means software enable, False means software disable)
        :type counters: dict<int: bool>

        :raises OSError: in case the operation fails
        """
        register = 0
        for counter, action in list(counters.items()):
            reg = 1 << (counter - 1)
            if not action:
                reg = reg << 16
            register |= reg
        self.write_reg("SOFT_ENABLE_DISABLE", register)

    def enable_counters_software(self, counters):
        """
        Software enables the given counters

        This is a convenience method for :meth:`set_counters_software_enable_disable`

        :param counters:
            a container of the counters to be software enabled. It can be any python
            container of integers (tuple, list, set, iterable, even dict)
        :type counters: container<int>

        :raises OSError: in case the operation fails
        """
        ct = {}
        for counter in counters:
            ct[counter] = True
        self.set_counters_software_enable_disable(ct)

    def disable_counters_software(self, counters):
        """
        Software disables the given counters

        This is a convenience method for :meth:`set_counters_software_enable_disable`

        :param counters:
            a container of the counters to be software disabled. It can be any python
            container of integers (tuple, list, iterable, even dict)
        :type counters: container<int>

        :raises OSError: in case the operation fails
        """
        ct = {}
        for counter in counters:
            ct[counter] = False
        self.set_counters_software_enable_disable(ct)

    def dump_memory_zones(self):
        """
        Dump internal card register memory

        Result is a sequence of memory zones. Each memory zone consists of an
        offset, and a copy of the card memory

        :return: the card memory dump separated by zones

        :rtype: sequence<sequence<offset, buffer>>
        """
        memory_zones = []
        last_zone = None
        for zone in CT2_R_SEQ:
            r0 = zone[0]
            offset, size = r0[0], len(zone) * CT2_REG_SIZE
            if r0[1] in ("CTRL_IT", "SOFT_ENABLE_DISABLE"):
                continue
            dump = self.interface.pread(offset, size)
            memory_zones.append((offset, dump))
        return memory_zones

    def dump_memory(self):
        """
        Dump internal card register memory

        :return:
            a buffer representing a copy of the card internal register memory
        :rtype: bytes
        """
        memory = []
        next_addr = None
        for offset, mem in self.dump_memory_zones():
            if next_addr is not None:
                # if there is a gap fill it with 0xFE
                memory.append((offset - next_addr) * b"\xFE")
            memory.append(mem)
            next_addr = offset + len(mem)
        return b"".join(memory)


class P201Card(BaseCard):
    """
    P201 card class
    """

    #: list of valid card counters
    COUNTERS = list(range(1, 13))

    #: list of valid card channels
    CHANNELS = list(range(1, 11))

    #: list of valid card input channels
    INPUT_CHANNELS = list(range(1, 11))

    #: list of valid card ouput channels
    OUTPUT_CHANNELS = list(range(9, 11))

    #: fifo size (bytes)
    FIFO_SIZE = 2048 * CT2_REG_SIZE


class C208Card(BaseCard):
    def __init__(self, *args, **kws):
        raise NotImplementedError


def get_ct2_card_class(card_type):
    if card_type is None or "P201" in card_type:
        klass = P201Card
    elif "C208" in card_type:
        klass = C208Card
    else:
        klass = None
    return klass


def CT2Card(card_type, address):
    klass = get_ct2_card_class(card_type)
    if not klass:
        raise ValueError("Invalid card_type: %s" % card_type)

    address = address if address else "/dev/ct2_0"
    return klass(CardInterface(address))


# -----------------------------------------------------------------------------
# Configuration helpers
# -----------------------------------------------------------------------------

DEFAULT_COUNTER_CONFIG = {
    "gate source": "GATE_CMPT",
    "start source": "SOFTWARE",
    "stop source": "SOFTWARE",
    "reset": False,
    "stop": False,
    "latch sources": (),
    "software enable": False,
    "interrupt": False,
    "latch triggers dma": False,
    "fifo on dma trigger": False,
    "comparator": 0,
    "clock source": None,
}


def default_counter_config(card, counter):
    ct_cfg = dict(DEFAULT_COUNTER_CONFIG, address=counter)
    if counter in card.CHANNELS:
        clock_source = "INC_CH_{0}_PULSE".format(counter)
    else:
        clock_source = "CLK_100_MHz"
    ct_cfg["clock source"] = clock_source
    return ct_cfg


DEFAULT_CHANNEL_INPUT_CONFIG = {"interrupt": (), "50 ohm": False, "level": "TTL"}


DEFAULT_CHANNEL_OUTPUT_CONFIG = {
    "level": "TTL",
    "software enable": False,
    "source": "SOFTWARE",
    "filter clock": "CLK_100_MHz",
    "filter enable": False,
    "polarity inverted": False,
}


def default_channel_config(card, channel):
    ch_cfg = dict(address=channel)
    if channel in card.INPUT_CHANNELS:
        ch_cfg["input"] = dict(DEFAULT_CHANNEL_INPUT_CONFIG)
    if channel in card.OUTPUT_CHANNELS:
        ch_cfg["output"] = dict(DEFAULT_CHANNEL_OUTPUT_CONFIG)
    return ch_cfg


__enum_meta = {
    #   enum           optional      default
    #                  prefixes       value
    Clock: (("CLK_",), Clock.CLK_100_MHz),
    FilterClock: (("CLK_",), FilterClock.CLK_100_MHz),
    CtClockSrc: (("CLK_",), CtClockSrc.CLK_1_25_KHz),
    CtGateSrc: ((), CtGateSrc.GATE_CMPT),
    CtHardStartSrc: ((), CtHardStartSrc.SOFTWARE),
    CtHardStopSrc: ((), CtHardStopSrc.SOFTWARE),
    Level: ((), Level.DISABLE),
    OutputSrc: (("CLK_",), OutputSrc.SOFTWARE),  # maybe default should be DISABLE ?
}


def __get_from_enum(enum, name):
    if name is None:
        return __enum_meta[enum][1]
    name_u = name.upper()
    repls = (
        (" ", "_"),
        (".", "_"),
        ("CHANNEL", "CH"),
        ("CLOCK", "CLK"),
        ("CHANNEL", "CH"),
        ("COUNTER", "CT"),
        ("EQUAL", "EQ"),
        ("COMPARE", "CMP"),
        ("MHZ", "MHz"),
        ("KHZ", "KHz"),
        ("INVERTED", "INV"),
        ("INVERT", "INV"),
    )
    for orig, repl in repls:
        name_u = name_u.replace(orig, repl)
    names = [name_u] + [prefix + name_u for prefix in __enum_meta[enum][0]]
    for n in names:
        try:
            return getattr(enum, n)
        except AttributeError:
            pass
    else:
        raise AttributeError("{0} does not have member {1}".format(enum, name))


def __get(cfg, name, default=None, klass=None):
    value = cfg.get(name, default)
    if klass is None:
        return value
    elif issubclass(klass, enum.Enum):
        return __get_from_enum(klass, value)


def __get_card_config(name):
    from bliss.config.static import get_config

    config = get_config()
    card_config = config.get_config(name)
    return card_config


def create_object_from_config_node(config, node):
    """
    To be used by the ct2 bliss config plugin
    """
    name = node.get("name")
    card = create_and_configure_card(node)
    return {name: card}, {name: card}


def create_and_configure_card(config_or_name):
    if isinstance(config_or_name, str):
        card_config = __get_card_config(config_or_name)
    else:
        card_config = config_or_name
    card = create_card_from_configure(card_config)
    configure_card(card, card_config)
    return card


def create_card_from_configure(config):
    """
    Create a card from the given configuration (beacon compatible)
    The card is just created with the address given by the configuration.
    It is not configured at all!

    :param config: configuration dictionary or dictionary like object
    :type config: dict
    :return: a new instance of :class:`P201`
    :rtype: :class:`P201`
    """
    return CT2Card(config.get("class", "P201"), config.get("address"))


def configure_card(card, config):
    """
    Configures the given card with the given configuration

    :param card: the card to be configured
    :type card: :class:`P201`
    :param config: configuration dictionary or dictionary like object
    :type config: dict
    """
    card.request_exclusive_access()
    card.set_interrupts()
    card.reset_FIFO_error_flags()

    if __get(config, "hard reset on init", False):
        card.reset()
    if __get(config, "soft reset on init", True):
        card.software_reset()

    card.set_clock(__get(config, "clock", klass=Clock, default="CLK_100_MHz"))

    dma_int = __get(config, "dma interrupt", False)
    fifo_hf_int = __get(config, "fifo half full interrupt", False)
    error_int = __get(config, "error interrupt", False)

    # Counters configuration

    ct_cfgs = {}
    ct_latch_srcs = {}
    ct_sw_enables = {}
    ct_ints = {}
    ct_latch_triggers_dma = {}
    ct_fifo_dma_trigger = {}
    ct_cmpts = {}

    ct_cfg_dict = dict(
        [(addr, default_counter_config(card, addr)) for addr in card.COUNTERS]
    )

    for counter in config.get("counters", ()):
        addr = int(counter["address"])
        ct_cfg_dict[addr].update(counter)

    for addr, counter in list(ct_cfg_dict.items()):
        ct_cfgs[addr] = CtConfig(
            clock_source=__get(counter, "clock source", klass=CtClockSrc),
            gate_source=__get(counter, "gate source", klass=CtGateSrc),
            hard_start_source=__get(counter, "start source", klass=CtHardStartSrc),
            hard_stop_source=__get(counter, "stop source", klass=CtHardStopSrc),
            reset_from_hard_soft_stop=__get(counter, "reset"),
            stop_from_hard_stop=__get(counter, "stop"),
        )

        for ct_latched in __get(counter, "latch sources"):
            ct_latch_srcs[ct_latched] = addr

        ct_sw_enables[addr] = __get(counter, "software enable")
        ct_ints[addr] = __get(counter, "interrupt")
        ct_latch_triggers_dma[addr] = __get(counter, "latch triggers dma")
        ct_fifo_dma_trigger[addr] = __get(counter, "fifo on dma trigger")
        ct_cmpts[addr] = __get(counter, "comparator")

    # Channels configuration

    ch_50_ohms = {}
    ch_ints = {}
    ch_in_levels = {}
    ch_out_levels = {}
    ch_out_sw = {}
    ch_out_srcs = {}
    ch_out_filters = {}

    ch_cfg_dict = dict(
        [(addr, default_channel_config(card, addr)) for addr in card.CHANNELS]
    )

    for channel in config.get("channels", ()):
        addr = int(channel["address"])
        ch_cfg = ch_cfg_dict[addr]
        if addr in card.INPUT_CHANNELS:
            ch_cfg["input"].update(channel.get("input", {}))
        if addr in card.OUTPUT_CHANNELS:
            ch_cfg["output"].update(channel.get("output", {}))

    for addr, channel in list(ch_cfg_dict.items()):
        if addr in card.INPUT_CHANNELS:
            inp = channel["input"]
            ints = list(map(string.lower, __get(inp, "interrupt")))
            ch_ints[addr] = TriggerInterrupt(
                rising="rising" in ints, falling="falling" in ints
            )
            ch_50_ohms[addr] = __get(inp, "50 ohm")
            level = __get(inp, "level").upper()
            try:
                level = Level[level]
            except KeyError:
                level = Level.DISABLE
            ch_in_levels[addr] = level

        if addr in card.OUTPUT_CHANNELS:
            out = channel["output"]
            ch_out_levels[addr] = __get(out, "level", klass=Level)
            ch_out_sw[addr] = __get(out, "software enable")
            ch_out_srcs[addr] = __get(out, "source", klass=OutputSrc)
            f_clk = __get(out, "filter clock", klass=FilterClock)
            f_enable = __get(out, "filter enable")
            f_pol_inv = __get(out, "polarity inverted")
            ch_out_filters[addr] = FilterOutput(
                clock=f_clk, enable=f_enable, polarity_inverted=f_pol_inv
            )

    card.set_input_channels_50ohm_adapter(ch_50_ohms)
    card.set_input_channels_level(ch_in_levels)

    card.set_output_channels_level(ch_out_levels)
    card.set_output_channels_software_enable(ch_out_sw)
    card.set_output_channels_source(ch_out_srcs)
    card.set_output_channels_filter(ch_out_filters)

    card.set_counters_config(ct_cfgs)
    card.set_counters_latch_sources(ct_latch_srcs)
    card.set_DMA_enable_trigger_latch(
        counters=ct_latch_triggers_dma, latches=ct_fifo_dma_trigger
    )
    card.set_counters_software_enable_disable(ct_sw_enables)
    card.set_counters_comparators_values(ct_cmpts)

    card.set_interrupts(ch_ints, ct_ints, dma_int, fifo_hf_int, error_int)


def main():
    # logging.basicConfig(level=logging.DEBUG)

    def out(msg):
        sys.stdout.write(msg)
        sys.stdout.flush()

    p201 = P201Card()
    p201.request_exclusive_access()
    p201.reset()
    p201.software_reset()

    # internal clock 100 Mhz
    p201.set_clock(Clock.CLK_100_MHz)

    # channel 10 output: counter 10 gate envelop
    p201.set_output_channels_level({10: Level.TTL})

    # no 50 ohm adapter
    p201.set_input_channels_50ohm_adapter({})

    # channel 9 and 10: no filter, no polarity inv
    p201.set_output_channels_filter({})

    # channel 10 output: counter 10 gate envelop
    p201.set_output_channels_source({10: OutputSrc.CT_10_GATE})

    # Internal clock to 1 Mhz [1us], Gate=1, Soft Start, HardStop on CMP,
    # Reset on Hard/SoftStop, Stop on HardStop
    ct10_config = CtConfig(
        clock_source=CtClockSrc.CLK_1_MHz,
        gate_source=CtGateSrc.GATE_CMPT,
        hard_start_source=CtHardStartSrc.SOFTWARE,
        hard_stop_source=CtHardStopSrc.CT_10_EQ_CMP_10,
        reset_from_hard_soft_stop=True,
        stop_from_hard_stop=True,
    )
    p201.set_counter_config(10, ct10_config)

    # Latch on Counter 10 HardStop
    p201.set_counters_latch_sources({10: 10})

    # Counter 10 will count 1 sec
    p201.set_counter_comparator_value(10, 1000 * 1000)

    started, start_count = False, 0
    while not started:
        # SoftStart on Counter 10
        start_count += 1
        if start_count > 10:
            print("failed to start after 10 atempts")
            break
        p201.set_counters_software_start_stop({10: True})
        status = p201.get_counters_status()
        started = status[10].run

    if start_count > 1:
        logging.warning("took %d times to start", start_count)

    if started:
        print("Started!")
        import time

        while True:
            time.sleep(0.1)
            counter = p201.get_counter_value(10)
            latch = p201.get_latch_value(10)
            status = p201.get_counters_status()
            if not status[10].run:
                break
            msg = "\r%07d %07d" % (counter, latch)
            out(msg)
        print("\n%07d %07d" % (counter, latch))

    p201.disable_counters_software((10,))

    import pprint

    pprint.pprint(p201.get_counters_status())
    p201.relinquish_exclusive_access()

    return p201


if __name__ == "__main__":
    main()
