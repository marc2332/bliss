
"""
The python module for the ct2 (P201/C208) ESRF PCI counter card
"""

from __future__ import print_function

import os
import sys
import errno
import fcntl
import ctypes
import ctypes.util
import struct
import logging
import weakref

try:
    import enum
except:
    import enum34 as enum


# low level pread and pwrite calls for the p201/c208 driver.

# even if we are using python >=  3.3 we cannot use os.pread/pwrite calls
# because of the semantics of the p201/c208 driver. For example, the read
# returns the number of adjacent registers that we actually read instead
# of the the number of bytes read like the linux programmer's manual specifies

__libc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('c'))

def pread(fd, offset):
    buff = ctypes.create_string_buffer(CT2_REG_SIZE)
    n = __libc.pread(fd, buff, 1, offset)
    if n == -1:
        err = ctypes.get_errno()
        if err != 0:
            ctypes.set_errno(0)
            raise OSError("pread error: %s (%d): %s" % (errno.errorcode(err),
                                                        err,
                                                        errno.strerror(err)))
        else:
            raise OSError("pread error")
    return buff[:]

def pwrite(fd, buff, offset):
    n = __libc.pwrite(fd, buff, 1, offset)
    if n == -1:
        err = ctypes.get_errno()
        if err != 0:
            ctypes.set_errno(0)
            raise OSError("pwrite error: %s (%d): %s" % (errno.errorcode(err),
                                                         err,
                                                         errno.strerror(err)))
        else:
            raise OSError("pwrite error")

#--------------------------------------------------------------------------
#                       Linux ioctl numbers made easy
#--------------------------------------------------------------------------

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
    if isinstance(size, str) or isinstance(size, unicode):
        size = struct.calcsize(size)
    return dir  << _IOC_DIRSHIFT  | \
           type << _IOC_TYPESHIFT | \
           nr   << _IOC_NRSHIFT   | \
           size << _IOC_SIZESHIFT


def _IO(type, nr): return _IOC(_IOC_NONE, type, nr, 0)
def _IOR(type, nr, size): return _IOC(_IOC_READ, type, nr, size)
def _IOW(type, nr, size): return _IOC(_IOC_WRITE, type, nr, size)
def _IOWR(type, nr, size): return _IOC(_IOC_READ | _IOC_WRITE, type, nr, size)

#--------------------------------------------------------------------------
#                                Helpers
#--------------------------------------------------------------------------

def NOT(a):
    return 0xFFFFFFFF ^ a


@enum.unique
class Edge(enum.Enum):
    DISABLE        = 0b00
    RISING         = 0b01
    FALLING        = 0b10
    RISING_FALLING = 0b11


@enum.unique
class Level(enum.Enum):
    DISABLE       = 0b00
    TTL           = 0b01
    NIM           = 0b10
    TTL_NIM       = 0b11


#==========================================================================
#                           Register Definitions
#==========================================================================

CT2_REG_SIZE = 4

class CT2Exception(Exception):
    pass


# R ... read with side effects
# W ... write with side effects
# r ... read without side effects (ie, with memory semantics)
# w ... write without side effects


#--------------------------------------------------------------------------
#                       PCI I/O Space 1 Registers Map
#--------------------------------------------------------------------------

CT2_R1_OFFSET = 0

CT2_R1_SEQ = [
# addr        name      read  write             description
[0x00, "COM_GENE",      True, True,  "General control"],
[0x04, "CTRL_GENE",     True, False, "General status"],
[0x0C, "NIVEAU_OUT",    True, True,  "Output enable and type (TTL or NIM)"],
[0x10, "ADAPT_50",      True, True,  "Input 50 ohms loads selector"],
[0x14, "SOFT_OUT",      True, True,  "Output status control (when enabled)"],
[0x18, "RD_IN_OUT",     True, False, "Input and output readback"],
[0x1C, "RD_CTRL_CMPT",  True, False, "Counter ENABLE and RUN readback"],
[0x20, "CMD_DMA",       True, True,  "DMA enable and trigger source, counters for storing selector"],
[0x24, "CTRL_FIFO_DMA", True, False, "FIFO status"],
[0x28, "SOURCE_IT_A",   True, True,  "Interrupt source A selector"],
[0x2C, "SOURCE_IT_B",   True, True,  "Interrupt source B selector"],
[0x30, "CTRL_IT",       True, False, "Interrupt status and clear"],
[0x34, "NIVEAU_IN",     True, True,  "Input level (TTL or NIM), selector"],

[0x40, "RD_CMPT_1",  True, False, "Counter 1 direct readout"],
[0x44, "RD_CMPT_2",  True, False, "Counter 2 direct readout"],
[0x48, "RD_CMPT_3",  True, False, "Counter 3 direct readout"],
[0x4C, "RD_CMPT_4",  True, False, "Counter 4 direct readout"],
[0x50, "RD_CMPT_5",  True, False, "Counter 5 direct readout"],
[0x54, "RD_CMPT_6",  True, False, "Counter 6 direct readout"],
[0x58, "RD_CMPT_7",  True, False, "Counter 7 direct readout"],
[0x5C, "RD_CMPT_8",  True, False, "Counter 8 direct readout"],
[0x60, "RD_CMPT_9",  True, False, "Counter 9 direct readout"],
[0x64, "RD_CMPT_10", True, False, "Counter 10 direct readout"],
[0x68, "RD_CMPT_11", True, False, "Counter 11 direct readout"],
[0x6C, "RD_CMPT_12", True, False, "Counter 12 direct readout"],

[0x70, "RD_LATCH_CMPT_1", True, False,  "Latch counter 1 readout"],
[0x74, "RD_LATCH_CMPT_2", True, False,  "Latch counter 2 readout"],
[0x78, "RD_LATCH_CMPT_3", True, False,  "Latch counter 3 readout"],
[0x7C, "RD_LATCH_CMPT_4", True, False,  "Latch counter 4 readout"],
[0x80, "RD_LATCH_CMPT_5", True, False,  "Latch counter 5 readout"],
[0x84, "RD_LATCH_CMPT_6", True, False,  "Latch counter 6 readout"],
[0x88, "RD_LATCH_CMPT_7", True, False,  "Latch counter 7 readout"],
[0x8C, "RD_LATCH_CMPT_8", True, False,  "Latch counter 8 readout"],
[0x90, "RD_LATCH_CMPT_9", True, False,  "Latch counter 9 readout"],
[0x94, "RD_LATCH_CMPT_10", True, False, "Latch counter 10 readout"],
[0x98, "RD_LATCH_CMPT_11", True, False, "Latch counter 11 readout"],
[0x9C, "RD_LATCH_CMPT_12", True, False, "Latch counter 12 readout"],

[0xFC, "TEST_REG", True, True, "Test data register"],
]

# make a dict, change the address: divide by register size + add the register map offset

CT2_R1_DICT = {}
for reg_info in CT2_R1_SEQ:
    addr, name, r, w, desc = reg_info
    addr = CT2_R1_OFFSET + addr / CT2_REG_SIZE
    reg_info[0] = addr
    CT2_R1_DICT[name] = addr, r, w, desc
del reg_info, addr, name, r, w, desc

#--------------------------------------------------------------------------
#                       PCI I/O Space 2 Registers Map
#--------------------------------------------------------------------------

CT2_R2_OFFSET = 64

CT2_R2_SEQ = [
# addr        name           read  write             description
[0x00, "SEL_FILTRE_INPUT_A", True, True, "Input 1 to 6: filter configuration and deglitcher enable"],
[0x04, "SEL_FILTRE_INPUT_B", True, True, "Input 7 to 10: filter configuration and deglitcher enable"],

[0x10, "SEL_FILTRE_OUTPUT", True, True, "Output 9 and 10: filter configuration and polarity selection"],

[0x1C, "SEL_SOURCE_OUTPUT", True, True, "Output 9 and 10: source selection"],

[0x20, "SEL_LATCH_A", True, True, "Counter 1 and 2: latch source"],
[0x24, "SEL_LATCH_B", True, True, "Counter 3 and 4: latch source"],
[0x28, "SEL_LATCH_C", True, True, "Counter 5 and 6: latch source"],
[0x2C, "SEL_LATCH_D", True, True, "Counter 7 and 8: latch source"],
[0x30, "SEL_LATCH_E", True, True, "Counter 9 and 10: latch source"],
[0x34, "SEL_LATCH_F", True, True, "Counter 11 and 12: latch source"],

[0x38, "CONF_CMPT_1", True, True,  "Counter 1: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x3C, "CONF_CMPT_2", True, True,  "Counter 2: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x40, "CONF_CMPT_3", True, True,  "Counter 3: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x44, "CONF_CMPT_4", True, True,  "Counter 4: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x48, "CONF_CMPT_5", True, True,  "Counter 5: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x4C, "CONF_CMPT_6", True, True,  "Counter 6: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x50, "CONF_CMPT_7", True, True,  "Counter 7: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x54, "CONF_CMPT_8", True, True,  "Counter 8: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x58, "CONF_CMPT_9", True, True,  "Counter 9: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x5C, "CONF_CMPT_10", True, True, "Counter 10: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x60, "CONF_CMPT_11", True, True, "Counter 11: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],
[0x64, "CONF_CMPT_12", True, True, "Counter 12: clk, gate_cmpt, hard_start, hard_stop source and reset / stop enable"],

[0x68, "SOFT_ENABLE_DISABLE", False, True, "Counters 1 to 12: software enable, disable"],
[0x6C, "SOFT_START_STOP",     False, True, "Counters 1 to 12: software start, stop"],
[0x70, "SOFT_LATCH",          False, True, "Counters 1 to 12: software latch"],

[0x74, "COMPARE_CMPT_1", True, True,  "Counter 1 comparator value"],
[0x78, "COMPARE_CMPT_2", True, True,  "Counter 2 comparator value"],
[0x7C, "COMPARE_CMPT_3", True, True,  "Counter 3 comparator value"],
[0x80, "COMPARE_CMPT_4", True, True,  "Counter 4 comparator value"],
[0x84, "COMPARE_CMPT_5", True, True,  "Counter 5 comparator value"],
[0x88, "COMPARE_CMPT_6", True, True,  "Counter 6 comparator value"],
[0x8C, "COMPARE_CMPT_7", True, True,  "Counter 7 comparator value"],
[0x90, "COMPARE_CMPT_8", True, True,  "Counter 8 comparator value"],
[0x94, "COMPARE_CMPT_9", True, True,  "Counter 9 comparator value"],
[0x98, "COMPARE_CMPT_10", True, True, "Counter 10 comparator value"],
[0x9C, "COMPARE_CMPT_11", True, True, "Counter 11 comparator value"],
[0xA0, "COMPARE_CMPT_12", True, True, "Counter 12 comparator value"],
]

# make a dict, change the address: divide by register size + add the register map offset

CT2_R2_DICT = {}
for reg_info in CT2_R2_SEQ:
    addr, name, r, w, desc = reg_info
    addr = CT2_R2_OFFSET + addr / CT2_REG_SIZE
    reg_info[0] = addr
    CT2_R2_DICT[name] = addr, r, w, desc
del reg_info, addr, name, r, w, desc

#--------------------------------------------------------------------------
#                       PCI I/O Registers Map
#--------------------------------------------------------------------------

CT2_R_SEQ = CT2_R1_SEQ + CT2_R2_SEQ
CT2_R_DICT = dict(CT2_R1_DICT)
CT2_R_DICT.update(CT2_R2_DICT)

#============================================================================
#                  BIT FIELDS, MASKS, OFFSETS, MACROS DEFINITIONS
#
# N.B. Masks/offsets that are valid for both C208 and P201 start with CT2_,
#      C208 specific start with C208_, P201 specif.start with P201_
#============================================================================

#----------------------------------------------------------------------------
# Definitions for "low" 12 bits (0-11) and "high" 12 (16-27) bits masks
#             used to mask useful bits in several registers.
#             Since cards have 12 counters and on C208 also 12 channels, the
#             usefull register part is either "low" or "high" 12 bits.
#             For P201 which has only 10 channels, provide also masks for
#             "low" 10 bits (0-9) and "high" 12 (16-25) bits.
#----------------------------------------------------------------------------
CT2_LO12BITS_MSK = 0x00000fff # Mask for bits 0-11
CT2_LO12BITS_OFF = 0          # Offset for the low word
CT2_HI12BITS_MSK = 0x0fff0000 # Mask for bits 16-27
CT2_HI12BITS_OFF = 16         # Offset for the high word
CT2_LO10BITS_MSK = 0x000003ff # Mask for bits 0-9
CT2_LO10BITS_OFF = 0          # Offset for the low word
CT2_HI10BITS_MSK = 0x03ff0000 # Mask for bits 16-25
CT2_HI10BITS_OFF = 16         # Offset for the high word


#--------------------------------------------------------------------------
#                         PCI I/O Space 1 Registers
#--------------------------------------------------------------------------

#--------------------------------------------------------------------------
# Definitions for the COM_GENE (general command) register(R/W)
#--------------------------------------------------------------------------
CT2_COM_GENE_UMSK       = 0x0000009f # Used bits mask
CT2_COM_GENE_ENAB_MSK   = 0x00000010 # en(1)/dis(0)able oscillator
CT2_COM_GENE_SOFT_RESET = 0x00000080 # soft reset(1)
CT2_COM_GENE_FREQ_MSK   = 0x0000000f # Frequency bitmask
CT2_COM_GENE_FREQ_OFF   = 0          # Frequency offset

@enum.unique
class Clock(enum.Enum):
    CLK_DISABLE   = 0b00000
    CLK_20_MHz    = 0b10101
    CLK_25_MHz    = 0b10100
    CLK_30_MHz    = 0b10010
    CLK_33_33_MHz = 0b10001
    CLK_40_MHz    = 0b11111
    CLK_45_MHz    = 0b11101
    CLK_50_MHz    = 0b11100
    CLK_60_MHz    = 0b11010
    CLK_66_66_MHz = 0b11001
    CLK_70_MHz    = 0b10110
    CLK_75_MHz    = 0b11000
    CLK_80_MHz    = 0b10111
    CLK_90_MHz    = 0b11110
    CLK_100_MHz   = 0b10000

#----------------------------------------------------------------------------
# Definitions for the CTRL_GENE (general control) register(R)
#----------------------------------------------------------------------------
C208_CTRL_GENE_UMSK       = 0xfcffff7f # Used bits mask
P201_CTRL_GENE_UMSK       = 0x0000ff0f # Used bits mask
CT2_CTRL_GENE_FIFO_MSK    = 0x0000000f # AMCC fifo flags mask
CT2_CTRL_GENE_FIFO_OFF	  = 0          # AMCC fifo flags offset
C208_CTRL_GENE_PLL_OK     = 0x00000010 # external PLL synchronised
C208_CTRL_GENE_TEMP_ALERT = 0x00000020 # Virtex T > 126 degrees
C208_CTRL_GENE_TEMP_OVERT = 0x00000040 # Virtex T >  99 degrees
CT2_CTRL_GENE_CARDN_MSK   = 0x0000ff00 # card(C208 or P201) ser.nb mask
CT2_CTRL_GENE_CARDN_OFF   = 8          # card serial number offset
C208_CTRL_GENE_MEZZN_MSK  = 0x00ff0000 # C208 mezzanine serial nb msk
C208_CTRL_GENE_MEZZN_OFF  = 16         # C208 mezz. serial nb offset
C208_CTRL_GENE_3_3V_STA   = 0x04000000 # status of 3.3V (1 = OK)
C208_CTRL_GENE_2_5V_STA   = 0x08000000 # status of 2.5V (1 = OK)
C208_CTRL_GENE_1_8V_STA   = 0x10000000 # status of 1.8V (1 = OK)
C208_CTRL_GENE_5V_STA     = 0x20000000 # status of   5V (1 = OK)
C208_CTRL_GENE_P12V_STA   = 0x40000000 # status of +12V (1 = OK)
C208_CTRL_GENE_M12V_STA   = 0x80000000 # status of -12V (1 = OK)
C208_CTRL_GENE_LV_MSK     = 0xfc000000 # LV status msk(all LVstogether)
C208_CTRL_GENE_LV_OFF     = 26         # offset for LV status

def C208_VOLTS_OK(genctrl):
    return ((BIT_TST(genctrl, C208_CTRL_GENE_3_3V_STA)) & \
                (BIT_TST(genctrl, C208_CTRL_GENE_2_5V_STA)) & \
                (BIT_TST(genctrl, C208_CTRL_GENE_1_8V_STA)) & \
                (BIT_TST(genctrl, C208_CTRL_GENE_5V_STA)) & \
                (BIT_TST(genctrl, C208_CTRL_GENE_P12V_STA)) & \
                (BIT_TST(genctrl, C208_CTRL_GENE_M12V_STA)))

#----------------------------------------------------------------------------
# Definitions for TEMPS (temperature) register(R) - only exists for C208
#----------------------------------------------------------------------------
C208_TEMPS_VIRTEX_TEMP_MSK = 0x0000007f # Virtex Temperature mask
C208_TEMPS_VIRTEX_TEMP_OFF = 0          # Virtex Temperature offset
C208_TEMPS_VREG_TEMP_MSK   = 0x00007f00 # Voltage(2.5V,1.8V)reg. T mask
C208_TEMPS_VREG_TEMP_OFF   = 8          # Voltage regulators T offset
C208_TEMPS_UMSK            = 0x00007f7f # Used bits mask

#----------------------------------------------------------------------------
# Definitions for NIVEAU_OUT (output level) register(R/W).
# Remark: Better name for this register would be CHAN_TYPE!
#----------------------------------------------------------------------------
# used bits mask
C208_NIVEAU_OUT_UMSK = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
P201_NIVEAU_OUT_UMSK = 0x03000300

#----------------------------------------------------------------------------
# Definitions for ADAPT_50 (en/disable 50 Ohm on input) register(R/W)
#----------------------------------------------------------------------------
C208_ADAPT_50_UMSK = CT2_LO12BITS_MSK  # Used bits mask
P201_ADAPT_50_UMSK = CT2_LO10BITS_MSK  # Used bits mask

#----------------------------------------------------------------------------
# Definitions for SOFT_OUT (soft output = like Digital Out) register(R/W)
#----------------------------------------------------------------------------
C208_SOFT_OUT_UMSK = CT2_LO12BITS_MSK  # Used bits mask
P201_SOFT_OUT_UMSK = 0x00000300        # Used bits mask

#----------------------------------------------------------------------------
# Definitions for RD_IN_OUT (Virtex I/O; like Digital IN) register(R)
#----------------------------------------------------------------------------
# used bits mask
C208_RD_IN_OUT_UMSK       = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
P201_RD_IN_OUT_UMSK       = 0x03000000 | CT2_LO10BITS_MSK
C208_RD_IN_OUT_INPUT_MSK  = CT2_LO12BITS_MSK  # Input  level mask
P201_RD_IN_OUT_INPUT_MSK  = CT2_LO10BITS_MSK  # Input  level mask
CT2_RD_IN_OUT_INPUT_OFF   = 0                # Input  level offset
C208_RD_IN_OUT_OUTPUT_MSK = CT2_HI12BITS_MSK  # Output level mask
C208_RD_IN_OUT_OUTPUT_OFF = CT2_HI12BITS_OFF  # Output level offset
P201_RD_IN_OUT_OUTPUT_MSK = 0x03000000       # Output level mask
P201_RD_IN_OUT_OUTPUT_OFF = 24               # Output level offset

#----------------------------------------------------------------------------
# Definitions for RD_CTRL_CMPT (counter run/enable status) register(R)
#----------------------------------------------------------------------------
# used bits mask
CT2_RD_CTRL_CMPT_UMSK      = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
CT2_RD_CTRL_CMPT_ENDIS_MSK = CT2_LO12BITS_MSK  # counter soft en/disable
CT2_RD_CTRL_CMPT_ENDIS_OFF = CT2_LO12BITS_OFF
CT2_RD_CTRL_CMPT_ACQ_MSK   = CT2_HI12BITS_MSK  # counter idle/running
CT2_RD_CTRL_CMPT_ACQ_OFF   = CT2_HI12BITS_OFF

#----------------------------------------------------------------------------
# Definitions for CMD_DMA (dma command) register(R/W)
#----------------------------------------------------------------------------
# used bits mask
CT2_CMD_DMA_UMSK         = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK | 0x80000000
CT2_CMD_DMA_TRIG_MSK     = CT2_LO12BITS_MSK  # DMA trigger condition
CT2_CMD_DMA_TRIG_OFF     = CT2_LO12BITS_OFF  #     choice
CT2_CMD_DMA_TRANS_MSK    = CT2_HI12BITS_MSK  # enable DMA transfer
CT2_CMD_DMA_TRANS_OFF    = CT2_HI12BITS_OFF  #     choice
CT2_CMD_DMA_TRANSALL_BIT = 31 # 1: overall enable of DMA transf
                              #           (if this bit is not set the latches
                              #            selected in bits 16-27 are not
                              #            transferred).
                              # 0: reset FIFOs and error memory

#----------------------------------------------------------------------------
# Definitions for CTRL_FIFO_DMA (dma control) register(R/W)
#----------------------------------------------------------------------------
# used bits mask
CT2_CTRL_DMA_UMSK               = CT2_LO12BITS_MSK | 0x001f0000
CT2_CTRL_DMA_NW_MSK             = CT2_LO12BITS_MSK #nb wrds in FIFO to rd
CT2_CTRL_DMA_NW_OFF             = CT2_LO12BITS_OFF
CT2_CTRL_DMA_ERR_MSK            = 0x00070000
CT2_CTRL_DMA_ERR_OFF            = 16
CT2_CTRL_DMA_ERR_TRIG_LOST_BIT  = 16    # 1: error one DMA trigger lost
CT2_CTRL_DMA_ERR_READ_FIFO_BIT  = 17    # 1: error during FIFO read
CT2_CTRL_DMA_ERR_WRITE_FIFO_BIT = 18    # 1: error during FIFO write
CT2_CTRL_DMA_FLAGS_MSK          = 0x00180000
CT2_CTRL_DMA_FLAGS_OFF          = 19
CT2_CTRL_DMA_FIFO_EMPTY_BIT     = 19    # 1: FIFO empty
CT2_CTRL_DMA_FIFO_FULL_BIT      = 20    # 1: FIFO full

#----------------------------------------------------------------------------
# Definitions for SOURCE_IT_A  register(R/W)
#----------------------------------------------------------------------------
# used bits mask
C208_SRC_IT_A_UMSK   = CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
P201_SRC_IT_A_UMSK   = CT2_LO10BITS_MSK | CT2_HI10BITS_MSK
C208_SRC_IT_A_RE_MSK = CT2_LO12BITS_MSK # IT src = Raising Edge
C208_SRC_IT_A_RE_OFF = CT2_LO12BITS_OFF
P201_SRC_IT_A_RE_MSK = CT2_LO10BITS_MSK # IT src = Raising Edge
P201_SRC_IT_A_RE_OFF = CT2_LO10BITS_OFF
C208_SRC_IT_A_FE_MSK = CT2_HI12BITS_MSK # IT src = Falling Edge
C208_SRC_IT_A_FE_OFF = CT2_HI12BITS_OFF
P201_SRC_IT_A_FE_MSK = CT2_HI10BITS_MSK # IT src = Falling Edge
P201_SRC_IT_A_FE_OFF = CT2_HI10BITS_OFF

#----------------------------------------------------------------------------
# Definitions for SOURCE_IT_B  register(R/W)
#----------------------------------------------------------------------------
# used bits mask
CT2_SRC_IT_B_UMSK        = CT2_LO12BITS_MSK | 0x00007000
CT2_SRC_IT_B_END_MSK     = CT2_LO12BITS_MSK  # IT src = END of counter
CT2_SRC_IT_B_END_OFF     = CT2_LO12BITS_OFF
CT2_SRC_IT_B_ENDFILL_BIT = 12 # IT at end of 1 cycle = 1 transfer of
                              #        selected latches into FIFO after DMA
                              #        trigger

CT2_SRC_IT_B_HALFFULL_BIT = 13 # IT at half fill FIFO after DMAtrig
CT2_SRC_IT_B_ERROR_BIT    = 14 # IT due to error (see CTRL_FIFO_DMA)

#----------------------------------------------------------------------------
# Definitions for CTRL_IT  register(R)
#----------------------------------------------------------------------------
# used bits mask
C208_CTRL_IT_UMSK       =  0x0effffff
P201_CTRL_IT_UMSK       =  0x0efff3ff
C208_CTRL_IT_REFE_MSK   =  CT2_LO12BITS_MSK  # IT = Rais./Fall. Edge
C208_CTRL_IT_REFE_OFF   =  CT2_LO12BITS_OFF
P201_CTRL_IT_REFE_MSK   =  CT2_LO10BITS_MSK  # IT = Rais./Fall. Edge
P201_CTRL_IT_REFE_OFF   =  CT2_LO10BITS_OFF
CT2_CTRL_IT_END_MSK     =  0x00fff000       # IT = END of ctn.0-11
CT2_CTRL_IT_END_OFF     =  12
CT2_CTRL_IT_ENDFILL_BIT =  25 # IT at end of 1 cycle = 1 transfer of
                              #          selected latches into FIFO after DMA
                              #          trigger

CT2_CTRL_IT_HALFFULL_BIT =  26 # IT at half fill FIFO after DMA trig
CT2_CTRL_IT_ERROR_BIT    =  27 # IT due to error (see CTRL_FIFO_DMA)

#----------------------------------------------------------------------------
# Definitions for NIVEAU_IN register(R/W) - only exists for P201
#----------------------------------------------------------------------------
P201_NIVEAU_IN_UMSK    = CT2_LO10BITS_MSK | CT2_HI10BITS_MSK
P201_NIVEAU_IN_TTL_MSK = CT2_LO10BITS_MSK  # TTL in level mask
P201_NIVEAU_IN_TTL_OFF = CT2_LO10BITS_OFF
P201_NIVEAU_IN_NIM_MSK = CT2_HI10BITS_MSK  # NIM in level mask
P201_NIVEAU_IN_NIM_OFF = CT2_HI10BITS_OFF

P201_OUT_9_TTL_ENABLE  = 1 << 8
P201_OUT_10_TTL_ENABLE = 1 << 9
P201_OUT_9_NIM_ENABLE  = 1 << 24
P201_OUT_10_NIM_ENABLE = 1 << 25

#--------------------------------------------------------------------------
#                         PCI I/O Space 2 Registers
#--------------------------------------------------------------------------

#----------------------------------------------------------------------------
# Definitions for SEL_FILTRE_INPUT_A/B (input filter select) registers (R/W)
#----------------------------------------------------------------------------
CT2_FILTRE_INPUT_UMSK           =   0x3fffffff
CT2_FILTRE_INPUT_FREQ_FIELD_MSK =   0x7  # freq. bit field needs 3 bits
CT2_FILTRE_INPUT_ONECHAN_WIDTH  =   5    # 5 bits cover input filter
                                         #       selection for each channel
CT2_FILTRE_INPUT_FILT_MODE_OFF  =    3    # offset of filter mode:
CT2_FILTRE_INPUT_FILT_MODE_SSPC =    0x0
CT2_FILTRE_INPUT_FILT_MODE_SYNC =    0x1
CT2_FILTRE_INPUT_FILT_MODE_SYM  =    0x2
CT2_FILTRE_INPUT_FILT_MODE_ASYM =    0x3
CT2_FILTRE_INPUT_FILT_MODE_MSK  =    0x3

#----------------------------------------------------------------------------
# Definitions for SEL_FILTRE_OUTPUT_A/B/C (output filter select) regs (R/W)
# For P201 only the last (= the 3rd) output filter reg. is used
#----------------------------------------------------------------------------
C208_FILTRE_OUTPUT_UMSK          = 0x3fffffff  # used bits mask
P201_FILTRE_OUTPUT_UMSK          = 0x00001f1f  # used bits mask
CT2_FILTRE_OUTPUT_FREQ_FIELD_MSK = 0x7  # freq bit field needs 3 bits
CT2_FILTRE_OUTPUT_ONECHAN_WIDTH  = 5    # 5 bits cover input filter
                                        #         selection for each channel
CT2_FILTRE_OUTPUT_FILTENAB_OFF   =  3   # offset of filter en/disable
                                        #         bit within 5 bits

CT2_FILTRE_OUTPUT_POLARITY_OFF   =  4   # offset of polarity inversion
                                        #         bit within 5 bits

@enum.unique
class FilterClock(enum.Enum):
    CLK_100_MHz  = 0x0
    CLK_12_5_MHz = 0x1
    CLK_1_MHz    = 0x2
    CLK_125_KHz  = 0x3
    CLK_10_KHz   = 0x4
    CLK_1_25_KHz = 0x5

#----------------------------------------------------------------------------
# Definitions for SEL_SOURCE_OUTPUT_A/B/C (output source select) regs (R/W)
# For P201 only the last (= the 3rd) output source reg. is used
#----------------------------------------------------------------------------
C208_SOURCE_OUTPUT_UMSK = 0x7f7f7f7f  # used bits mask
P201_SOURCE_OUTPUT_UMSK = 0x00007f7f  # used bits mask

@enum.unique
class OutputSrc(enum.Enum):
    CLK_SOFTWARE = 0x00
    CLK_1_25_KHz = 0x01
    CLK_10_KHz   = 0x02
    CLK_125_KHz  = 0x03
    CLK_1_MHz    = 0x04
    CLK_12_5_MHz = 0x05
    CLK_DISABLE  = 0x06

    CH_1_INPUT  = 0x07
    CH_2_INPUT  = 0x08
    CH_3_INPUT  = 0x09
    CH_4_INPUT  = 0x0A
    CH_5_INPUT  = 0x0B
    CH_6_INPUT  = 0x0C
    CH_7_INPUT  = 0x0D
    CH_8_INPUT  = 0x0E
    CH_9_INPUT  = 0x0F
    CH_10_INPUT = 0x10

    CH_1_INPUT_INV  = 0x13
    CH_2_INPUT_INV  = 0x14
    CH_3_INPUT_INV  = 0x15
    CH_4_INPUT_INV  = 0x16
    CH_5_INPUT_INV  = 0x17
    CH_6_INPUT_INV  = 0x18
    CH_7_INPUT_INV  = 0x19
    CH_8_INPUT_INV  = 0x1A
    CH_9_INPUT_INV  = 0x1B
    CH_10_INPUT_INV = 0x1C

    CH_1_RISING  = 0x1F
    CH_2_RISING  = 0x20
    CH_3_RISING  = 0x21
    CH_4_RISING  = 0x22
    CH_5_RISING  = 0x23
    CH_6_RISING  = 0x24
    CH_7_RISING  = 0x25
    CH_8_RISING  = 0x26
    CH_9_RISING  = 0x27
    CH_10_RISING  = 0x28

    CH_1_FALLING  = 0x2B
    CH_2_FALLING  = 0x2C
    CH_3_FALLING  = 0x2D
    CH_4_FALLING  = 0x2E
    CH_5_FALLING  = 0x2F
    CH_6_FALLING  = 0x30
    CH_7_FALLING  = 0x31
    CH_8_FALLING  = 0x32
    CH_9_FALLING  = 0x33
    CH_10_FALLING  = 0x34

    CH_1_RISING_FALLING  = 0x37
    CH_2_RISING_FALLING  = 0x38
    CH_3_RISING_FALLING  = 0x39
    CH_4_RISING_FALLING  = 0x3A
    CH_5_RISING_FALLING  = 0x3B
    CH_6_RISING_FALLING  = 0x3C
    CH_7_RISING_FALLING  = 0x3D
    CH_8_RISING_FALLING  = 0x3E
    CH_9_RISING_FALLING  = 0x3F
    CH_10_RISING_FALLING  = 0x40

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

#----------------------------------------------------------------------------
# Definitions for SEL_LATCH_A/B/C/D/E/F (latch select) registers (R/W)
# ctn = [0,11] = counter number
#----------------------------------------------------------------------------
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
class LatchCtSrc(enum.Enum):
    """
    Select counter source for latch
    """



#----------------------------------------------------------------------------
# Definitions for CONF_CMPT_1/12 (counter configuration) registers (R/W)
#----------------------------------------------------------------------------
CT2_CONF_CMPT_UMSK        =  0xc7ffffff	# Used bits mask
CT2_CONF_CMPT_CLK_MSK     =  0x0000007f
CT2_CONF_CMPT_CLK_OFF     =  0
CT2_CONF_CMPT_CLK_100_MHz =  0x5
CT2_CONF_CMPT_GATE_MSK    =  0x00001f80
CT2_CONF_CMPT_GATE_OFF    =  7
CT2_CONF_CMPT_HSTART_MSK  =  0x000fe000
CT2_CONF_CMPT_HSTART_OFF  =  13
CT2_CONF_CMPT_HSTOP_MSK   =  0x07f00000
CT2_CONF_CMPT_HSTOP_OFF   =  20
CT2_CONF_CMPT_RESET_BIT   =  30
CT2_CONF_CMPT_STOP_BIT    =  31
CT2_CONF_CMPT_RESET_MSK   =  1 << CT2_CONF_CMPT_RESET_BIT
CT2_CONF_CMPT_STOP_MSK    =  1 << CT2_CONF_CMPT_STOP_BIT

@enum.unique
class CtClockSrc(enum.Enum):
    """
    Count Clock Source enumeration. To be used in :class:`CtConfig`.
    """

    CLK_1_25_KHz = 0x00
    CLK_10_KHz   = 0x01
    CLK_125_KHz  = 0x02
    CLK_1_MHz    = 0x03
    CLK_12_5_MHz = 0x04
    CLK_100_MHz  = 0x05

    CH_1_RISING_EDGE  = 0x06
    CH_2_RISING_EDGE  = 0x07
    CH_3_RISING_EDGE  = 0x08
    CH_4_RISING_EDGE  = 0x09
    CH_5_RISING_EDGE  = 0x0A
    CH_6_RISING_EDGE  = 0x0B
    CH_7_RISING_EDGE  = 0x0C
    CH_8_RISING_EDGE  = 0x0D
    CH_9_RISING_EDGE  = 0x0E
    CH_10_RISING_EDGE = 0x0F

    CH_1_FALLING_EDGE  = 0x12
    CH_2_FALLING_EDGE  = 0x13
    CH_3_FALLING_EDGE  = 0x14
    CH_4_FALLING_EDGE  = 0x15
    CH_5_FALLING_EDGE  = 0x16
    CH_6_FALLING_EDGE  = 0x17
    CH_7_FALLING_EDGE  = 0x18
    CH_8_FALLING_EDGE  = 0x19
    CH_9_FALLING_EDGE  = 0x1A
    CH_10_FALLING_EDGE = 0x1B

    CH_1_RISING_FALLING_EDGE  = 0x1E
    CH_2_RISING_FALLING_EDGE  = 0x1F
    CH_3_RISING_FALLING_EDGE  = 0x20
    CH_4_RISING_FALLING_EDGE  = 0x21
    CH_5_RISING_FALLING_EDGE  = 0x22
    CH_6_RISING_FALLING_EDGE  = 0x23
    CH_7_RISING_FALLING_EDGE  = 0x24
    CH_8_RISING_FALLING_EDGE  = 0x25
    CH_9_RISING_FALLING_EDGE  = 0X26
    CH_10_RISING_FALLING_EDGE = 0x27

    INC_CT_1_START  = 0x2A
    INC_CT_2_START  = 0x2B
    INC_CT_3_START  = 0x2C
    INC_CT_4_START  = 0x2D
    INC_CT_5_START  = 0x2E
    INC_CT_6_START  = 0x2F
    INC_CT_7_START  = 0x30
    INC_CT_8_START  = 0x31
    INC_CT_9_START  = 0x32
    INC_CT_10_START = 0x33
    INC_CT_11_START = 0x34
    INC_CT_12_START = 0x35

    INC_CT_1_STOP  = 0x36
    INC_CT_2_STOP  = 0x37
    INC_CT_3_STOP  = 0x38
    INC_CT_4_STOP  = 0x39
    INC_CT_5_STOP  = 0x3A
    INC_CT_6_STOP  = 0x3B
    INC_CT_7_STOP  = 0x3C
    INC_CT_8_STOP  = 0x3D
    INC_CT_9_STOP  = 0x3E
    INC_CT_10_STOP = 0x3F
    INC_CT_11_STOP = 0x40
    INC_CT_12_STOP = 0x41

    INC_CT_1_START_STOP  = 0x42
    INC_CT_2_START_STOP  = 0x43
    INC_CT_3_START_STOP  = 0x44
    INC_CT_4_START_STOP  = 0x45
    INC_CT_5_START_STOP  = 0x46
    INC_CT_6_START_STOP  = 0x47
    INC_CT_7_START_STOP  = 0x48
    INC_CT_8_START_STOP  = 0x49
    INC_CT_9_START_STOP  = 0x4A
    INC_CT_10_START_STOP = 0x4B
    INC_CT_11_START_STOP = 0x4C
    INC_CT_12_START_STOP = 0x4D

    INC_CH_1_PULSE  = 0x4E
    INC_CH_2_PULSE  = 0x4F
    INC_CH_3_PULSE  = 0x50
    INC_CH_4_PULSE  = 0x51
    INC_CH_5_PULSE  = 0x52
    INC_CH_6_PULSE  = 0x53
    INC_CH_7_PULSE  = 0x54
    INC_CH_8_PULSE  = 0x55
    INC_CH_9_PULSE  = 0x56
    INC_CH_10_PULSE = 0x57


@enum.unique
class CtGateSrc(enum.Enum):

    GATE_CMPT = 0x00 << CT2_CONF_CMPT_GATE_OFF

    CH_1_INPUT  = 0x01 << CT2_CONF_CMPT_GATE_OFF
    CH_2_INPUT  = 0x02 << CT2_CONF_CMPT_GATE_OFF
    CH_3_INPUT  = 0x03 << CT2_CONF_CMPT_GATE_OFF
    CH_4_INPUT  = 0x04 << CT2_CONF_CMPT_GATE_OFF
    CH_5_INPUT  = 0x05 << CT2_CONF_CMPT_GATE_OFF
    CH_6_INPUT  = 0x06 << CT2_CONF_CMPT_GATE_OFF
    CH_7_INPUT  = 0x07 << CT2_CONF_CMPT_GATE_OFF
    CH_8_INPUT  = 0x08 << CT2_CONF_CMPT_GATE_OFF
    CH_9_INPUT  = 0x09 << CT2_CONF_CMPT_GATE_OFF
    CH_10_INPUT = 0x0A << CT2_CONF_CMPT_GATE_OFF

    CH_1_INPUT_INV  = 0x0D << CT2_CONF_CMPT_GATE_OFF
    CH_2_INPUT_INV  = 0x0E << CT2_CONF_CMPT_GATE_OFF
    CH_3_INPUT_INV  = 0x0F << CT2_CONF_CMPT_GATE_OFF
    CH_4_INPUT_INV  = 0x10 << CT2_CONF_CMPT_GATE_OFF
    CH_5_INPUT_INV  = 0x11 << CT2_CONF_CMPT_GATE_OFF
    CH_6_INPUT_INV  = 0x12 << CT2_CONF_CMPT_GATE_OFF
    CH_7_INPUT_INV  = 0x13 << CT2_CONF_CMPT_GATE_OFF
    CH_8_INPUT_INV  = 0x14 << CT2_CONF_CMPT_GATE_OFF
    CH_9_INPUT_INV  = 0x15 << CT2_CONF_CMPT_GATE_OFF
    CH_10_INPUT_INV = 0x16 << CT2_CONF_CMPT_GATE_OFF

    CT_1_GATE_ENVELOP  = 0x19 << CT2_CONF_CMPT_GATE_OFF
    CT_2_GATE_ENVELOP  = 0x1A << CT2_CONF_CMPT_GATE_OFF
    CT_3_GATE_ENVELOP  = 0x1B << CT2_CONF_CMPT_GATE_OFF
    CT_4_GATE_ENVELOP  = 0x1C << CT2_CONF_CMPT_GATE_OFF
    CT_5_GATE_ENVELOP  = 0x1D << CT2_CONF_CMPT_GATE_OFF
    CT_6_GATE_ENVELOP  = 0x1E << CT2_CONF_CMPT_GATE_OFF
    CT_7_GATE_ENVELOP  = 0x1F << CT2_CONF_CMPT_GATE_OFF
    CT_8_GATE_ENVELOP  = 0x20 << CT2_CONF_CMPT_GATE_OFF
    CT_9_GATE_ENVELOP  = 0x21 << CT2_CONF_CMPT_GATE_OFF
    CT_10_GATE_ENVELOP = 0x22 << CT2_CONF_CMPT_GATE_OFF
    CT_11_GATE_ENVELOP = 0x23 << CT2_CONF_CMPT_GATE_OFF
    CT_12_GATE_ENVELOP = 0x24 << CT2_CONF_CMPT_GATE_OFF

    CT_1_SWITCH_SIGNAL  = 0x25 << CT2_CONF_CMPT_GATE_OFF
    CT_2_SWITCH_SIGNAL  = 0x26 << CT2_CONF_CMPT_GATE_OFF
    CT_3_SWITCH_SIGNAL  = 0x27 << CT2_CONF_CMPT_GATE_OFF
    CT_4_SWITCH_SIGNAL  = 0x28 << CT2_CONF_CMPT_GATE_OFF
    CT_5_SWITCH_SIGNAL  = 0x29 << CT2_CONF_CMPT_GATE_OFF
    CT_6_SWITCH_SIGNAL  = 0x2A << CT2_CONF_CMPT_GATE_OFF
    CT_7_SWITCH_SIGNAL  = 0x2B << CT2_CONF_CMPT_GATE_OFF
    CT_8_SWITCH_SIGNAL  = 0x2C << CT2_CONF_CMPT_GATE_OFF
    CT_9_SWITCH_SIGNAL  = 0x2D << CT2_CONF_CMPT_GATE_OFF
    CT_10_SWITCH_SIGNAL = 0x2E << CT2_CONF_CMPT_GATE_OFF
    CT_11_SWITCH_SIGNAL = 0x2F << CT2_CONF_CMPT_GATE_OFF
    CT_12_SWITCH_SIGNAL = 0x30 << CT2_CONF_CMPT_GATE_OFF


@enum.unique
class CtHardStartSrc(enum.Enum):

    SOFTWARE_ONLY = 0x00 << CT2_CONF_CMPT_HSTART_OFF

    CH_1_RISING_EDGE  = 0x01 << CT2_CONF_CMPT_HSTART_OFF
    CH_2_RISING_EDGE  = 0x02 << CT2_CONF_CMPT_HSTART_OFF
    CH_3_RISING_EDGE  = 0x03 << CT2_CONF_CMPT_HSTART_OFF
    CH_4_RISING_EDGE  = 0x04 << CT2_CONF_CMPT_HSTART_OFF
    CH_5_RISING_EDGE  = 0x05 << CT2_CONF_CMPT_HSTART_OFF
    CH_6_RISING_EDGE  = 0x06 << CT2_CONF_CMPT_HSTART_OFF
    CH_7_RISING_EDGE  = 0x07 << CT2_CONF_CMPT_HSTART_OFF
    CH_8_RISING_EDGE  = 0x08 << CT2_CONF_CMPT_HSTART_OFF
    CH_9_RISING_EDGE  = 0x09 << CT2_CONF_CMPT_HSTART_OFF
    CH_10_RISING_EDGE = 0x0A << CT2_CONF_CMPT_HSTART_OFF

    CH_1_FALLING_EDGE  = 0x0D << CT2_CONF_CMPT_HSTART_OFF
    CH_2_FALLING_EDGE  = 0x0E << CT2_CONF_CMPT_HSTART_OFF
    CH_3_FALLING_EDGE  = 0x0F << CT2_CONF_CMPT_HSTART_OFF
    CH_4_FALLING_EDGE  = 0x10 << CT2_CONF_CMPT_HSTART_OFF
    CH_5_FALLING_EDGE  = 0x11 << CT2_CONF_CMPT_HSTART_OFF
    CH_6_FALLING_EDGE  = 0x12 << CT2_CONF_CMPT_HSTART_OFF
    CH_7_FALLING_EDGE  = 0x13 << CT2_CONF_CMPT_HSTART_OFF
    CH_8_FALLING_EDGE  = 0x14 << CT2_CONF_CMPT_HSTART_OFF
    CH_9_FALLING_EDGE  = 0x15 << CT2_CONF_CMPT_HSTART_OFF
    CH_10_FALLING_EDGE = 0x16 << CT2_CONF_CMPT_HSTART_OFF

    CH_1_RISING_FALLING_EDGE  = 0x19 << CT2_CONF_CMPT_HSTART_OFF
    CH_2_RISING_FALLING_EDGE  = 0x1A << CT2_CONF_CMPT_HSTART_OFF
    CH_3_RISING_FALLING_EDGE  = 0x1B << CT2_CONF_CMPT_HSTART_OFF
    CH_4_RISING_FALLING_EDGE  = 0x1C << CT2_CONF_CMPT_HSTART_OFF
    CH_5_RISING_FALLING_EDGE  = 0x1D << CT2_CONF_CMPT_HSTART_OFF
    CH_6_RISING_FALLING_EDGE  = 0x1E << CT2_CONF_CMPT_HSTART_OFF
    CH_7_RISING_FALLING_EDGE  = 0x1F << CT2_CONF_CMPT_HSTART_OFF
    CH_8_RISING_FALLING_EDGE  = 0x20 << CT2_CONF_CMPT_HSTART_OFF
    CH_9_RISING_FALLING_EDGE  = 0X21 << CT2_CONF_CMPT_HSTART_OFF
    CH_10_RISING_FALLING_EDGE = 0x22 << CT2_CONF_CMPT_HSTART_OFF

    CT_1_START  = 0x25 << CT2_CONF_CMPT_HSTART_OFF
    CT_2_START  = 0x26 << CT2_CONF_CMPT_HSTART_OFF
    CT_3_START  = 0x27 << CT2_CONF_CMPT_HSTART_OFF
    CT_4_START  = 0x28 << CT2_CONF_CMPT_HSTART_OFF
    CT_5_START  = 0x29 << CT2_CONF_CMPT_HSTART_OFF
    CT_6_START  = 0x2A << CT2_CONF_CMPT_HSTART_OFF
    CT_7_START  = 0x2B << CT2_CONF_CMPT_HSTART_OFF
    CT_8_START  = 0x2C << CT2_CONF_CMPT_HSTART_OFF
    CT_9_START  = 0x2D << CT2_CONF_CMPT_HSTART_OFF
    CT_10_START = 0x2E << CT2_CONF_CMPT_HSTART_OFF
    CT_11_START = 0x2F << CT2_CONF_CMPT_HSTART_OFF
    CT_12_START = 0x30 << CT2_CONF_CMPT_HSTART_OFF

    CT_1_STOP  = 0x31 << CT2_CONF_CMPT_HSTART_OFF
    CT_2_STOP  = 0x32 << CT2_CONF_CMPT_HSTART_OFF
    CT_3_STOP  = 0x33 << CT2_CONF_CMPT_HSTART_OFF
    CT_4_STOP  = 0x34 << CT2_CONF_CMPT_HSTART_OFF
    CT_5_STOP  = 0x35 << CT2_CONF_CMPT_HSTART_OFF
    CT_6_STOP  = 0x36 << CT2_CONF_CMPT_HSTART_OFF
    CT_7_STOP  = 0x37 << CT2_CONF_CMPT_HSTART_OFF
    CT_8_STOP  = 0x38 << CT2_CONF_CMPT_HSTART_OFF
    CT_9_STOP  = 0x39 << CT2_CONF_CMPT_HSTART_OFF
    CT_10_STOP = 0x3A << CT2_CONF_CMPT_HSTART_OFF
    CT_11_STOP = 0x3B << CT2_CONF_CMPT_HSTART_OFF
    CT_12_STOP = 0x3C << CT2_CONF_CMPT_HSTART_OFF

    CT_1_START_STOP  = 0x3D << CT2_CONF_CMPT_HSTART_OFF
    CT_2_START_STOP  = 0x3E << CT2_CONF_CMPT_HSTART_OFF
    CT_3_START_STOP  = 0x3F << CT2_CONF_CMPT_HSTART_OFF
    CT_4_START_STOP  = 0x40 << CT2_CONF_CMPT_HSTART_OFF
    CT_5_START_STOP  = 0x41 << CT2_CONF_CMPT_HSTART_OFF
    CT_6_START_STOP  = 0x42 << CT2_CONF_CMPT_HSTART_OFF
    CT_7_START_STOP  = 0x43 << CT2_CONF_CMPT_HSTART_OFF
    CT_8_START_STOP  = 0x44 << CT2_CONF_CMPT_HSTART_OFF
    CT_9_START_STOP  = 0x45 << CT2_CONF_CMPT_HSTART_OFF
    CT_10_START_STOP = 0x46 << CT2_CONF_CMPT_HSTART_OFF
    CT_11_START_STOP = 0x47 << CT2_CONF_CMPT_HSTART_OFF
    CT_12_START_STOP = 0x48 << CT2_CONF_CMPT_HSTART_OFF

    CT_1_EQ_CMP_1   = 0x49 << CT2_CONF_CMPT_HSTART_OFF
    CT_2_EQ_CMP_2   = 0x4A << CT2_CONF_CMPT_HSTART_OFF
    CT_3_EQ_CMP_3   = 0x4B << CT2_CONF_CMPT_HSTART_OFF
    CT_4_EQ_CMP_4   = 0x4C << CT2_CONF_CMPT_HSTART_OFF
    CT_5_EQ_CMP_5   = 0x4D << CT2_CONF_CMPT_HSTART_OFF
    CT_6_EQ_CMP_6   = 0x4E << CT2_CONF_CMPT_HSTART_OFF
    CT_7_EQ_CMP_7   = 0x4F << CT2_CONF_CMPT_HSTART_OFF
    CT_8_EQ_CMP_8   = 0x50 << CT2_CONF_CMPT_HSTART_OFF
    CT_9_EQ_CMP_9   = 0x51 << CT2_CONF_CMPT_HSTART_OFF
    CT_10_EQ_CMP_10 = 0x52 << CT2_CONF_CMPT_HSTART_OFF
    CT_11_EQ_CMP_11 = 0x53 << CT2_CONF_CMPT_HSTART_OFF
    CT_12_EQ_CMP_12 = 0x54 << CT2_CONF_CMPT_HSTART_OFF


@enum.unique
class CtHardStopSrc(enum.Enum):

    SOFTWARE_ONLY = 0x00 << CT2_CONF_CMPT_HSTOP_OFF

    CH_1_RISING_EDGE  = 0x01 << CT2_CONF_CMPT_HSTOP_OFF
    CH_2_RISING_EDGE  = 0x02 << CT2_CONF_CMPT_HSTOP_OFF
    CH_3_RISING_EDGE  = 0x03 << CT2_CONF_CMPT_HSTOP_OFF
    CH_4_RISING_EDGE  = 0x04 << CT2_CONF_CMPT_HSTOP_OFF
    CH_5_RISING_EDGE  = 0x05 << CT2_CONF_CMPT_HSTOP_OFF
    CH_6_RISING_EDGE  = 0x06 << CT2_CONF_CMPT_HSTOP_OFF
    CH_7_RISING_EDGE  = 0x07 << CT2_CONF_CMPT_HSTOP_OFF
    CH_8_RISING_EDGE  = 0x08 << CT2_CONF_CMPT_HSTOP_OFF
    CH_9_RISING_EDGE  = 0x09 << CT2_CONF_CMPT_HSTOP_OFF
    CH_10_RISING_EDGE = 0x0A << CT2_CONF_CMPT_HSTOP_OFF

    CH_1_FALLING_EDGE  = 0x0D << CT2_CONF_CMPT_HSTOP_OFF
    CH_2_FALLING_EDGE  = 0x0E << CT2_CONF_CMPT_HSTOP_OFF
    CH_3_FALLING_EDGE  = 0x0F << CT2_CONF_CMPT_HSTOP_OFF
    CH_4_FALLING_EDGE  = 0x10 << CT2_CONF_CMPT_HSTOP_OFF
    CH_5_FALLING_EDGE  = 0x11 << CT2_CONF_CMPT_HSTOP_OFF
    CH_6_FALLING_EDGE  = 0x12 << CT2_CONF_CMPT_HSTOP_OFF
    CH_7_FALLING_EDGE  = 0x13 << CT2_CONF_CMPT_HSTOP_OFF
    CH_8_FALLING_EDGE  = 0x14 << CT2_CONF_CMPT_HSTOP_OFF
    CH_9_FALLING_EDGE  = 0x15 << CT2_CONF_CMPT_HSTOP_OFF
    CH_10_FALLING_EDGE = 0x16 << CT2_CONF_CMPT_HSTOP_OFF

    CH_1_RISING_FALLING_EDGE  = 0x19 << CT2_CONF_CMPT_HSTOP_OFF
    CH_2_RISING_FALLING_EDGE  = 0x1A << CT2_CONF_CMPT_HSTOP_OFF
    CH_3_RISING_FALLING_EDGE  = 0x1B << CT2_CONF_CMPT_HSTOP_OFF
    CH_4_RISING_FALLING_EDGE  = 0x1C << CT2_CONF_CMPT_HSTOP_OFF
    CH_5_RISING_FALLING_EDGE  = 0x1D << CT2_CONF_CMPT_HSTOP_OFF
    CH_6_RISING_FALLING_EDGE  = 0x1E << CT2_CONF_CMPT_HSTOP_OFF
    CH_7_RISING_FALLING_EDGE  = 0x1F << CT2_CONF_CMPT_HSTOP_OFF
    CH_8_RISING_FALLING_EDGE  = 0x20 << CT2_CONF_CMPT_HSTOP_OFF
    CH_9_RISING_FALLING_EDGE  = 0X21 << CT2_CONF_CMPT_HSTOP_OFF
    CH_10_RISING_FALLING_EDGE = 0x22 << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_START  = 0x25 << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_START  = 0x26 << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_START  = 0x27 << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_START  = 0x28 << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_START  = 0x29 << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_START  = 0x2A << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_START  = 0x2B << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_START  = 0x2C << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_START  = 0x2D << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_START = 0x2E << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_START = 0x2F << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_START = 0x30 << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_STOP  = 0x31 << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_STOP  = 0x32 << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_STOP  = 0x33 << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_STOP  = 0x34 << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_STOP  = 0x35 << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_STOP  = 0x36 << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_STOP  = 0x37 << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_STOP  = 0x38 << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_STOP  = 0x39 << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_STOP = 0x3A << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_STOP = 0x3B << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_STOP = 0x3C << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_START_STOP  = 0x3D << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_START_STOP  = 0x3E << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_START_STOP  = 0x3F << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_START_STOP  = 0x40 << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_START_STOP  = 0x41 << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_START_STOP  = 0x42 << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_START_STOP  = 0x43 << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_START_STOP  = 0x44 << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_START_STOP  = 0x45 << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_START_STOP = 0x46 << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_START_STOP = 0x47 << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_START_STOP = 0x48 << CT2_CONF_CMPT_HSTOP_OFF

    CT_1_EQ_CMP_1   = 0x49 << CT2_CONF_CMPT_HSTOP_OFF
    CT_2_EQ_CMP_2   = 0x4A << CT2_CONF_CMPT_HSTOP_OFF
    CT_3_EQ_CMP_3   = 0x4B << CT2_CONF_CMPT_HSTOP_OFF
    CT_4_EQ_CMP_4   = 0x4C << CT2_CONF_CMPT_HSTOP_OFF
    CT_5_EQ_CMP_5   = 0x4D << CT2_CONF_CMPT_HSTOP_OFF
    CT_6_EQ_CMP_6   = 0x4E << CT2_CONF_CMPT_HSTOP_OFF
    CT_7_EQ_CMP_7   = 0x4F << CT2_CONF_CMPT_HSTOP_OFF
    CT_8_EQ_CMP_8   = 0x50 << CT2_CONF_CMPT_HSTOP_OFF
    CT_9_EQ_CMP_9   = 0x51 << CT2_CONF_CMPT_HSTOP_OFF
    CT_10_EQ_CMP_10 = 0x52 << CT2_CONF_CMPT_HSTOP_OFF
    CT_11_EQ_CMP_11 = 0x53 << CT2_CONF_CMPT_HSTOP_OFF
    CT_12_EQ_CMP_12 = 0x54 << CT2_CONF_CMPT_HSTOP_OFF


#----------------------------------------------------------------------------
# Definitions for SOFT_ENABLE_DISABLE register (W)
# reg = value of soft_enable_disable register, ctn = [0,11] = counter number
#----------------------------------------------------------------------------
# used bits mask
CT2_SOFT_ENABLE_DISABLE_UMSK =  CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
CT2_SOFT_ENABLE_ALL_MSK      =   CT2_LO12BITS_MSK
CT2_SOFT_ENABLE_ALL_OFF      =   CT2_LO12BITS_OFF
CT2_SOFT_DISABLE_ALL_MSK     =   CT2_HI12BITS_MSK
CT2_SOFT_DISABLE_ALL_OFF     =   CT2_HI12BITS_OFF

def CT2_SOFT_ENABLE(reg,ctn):
    return BIT_SETB(reg,ctn)
def CT2_SOFT_DISABLE(reg,ctn):
    return BIT_SETB(reg,ctn+16)

#----------------------------------------------------------------------------
# Definitions for SOFT_START_STOP register (W)
# reg = value of soft_start_stop register, crn = [0,11] = counter number
#----------------------------------------------------------------------------
# used bits mask
CT2_SOFT_START_STOP_UMSK =  CT2_LO12BITS_MSK | CT2_HI12BITS_MSK
CT2_SOFT_START_ALL_MSK   =  CT2_LO12BITS_MSK
CT2_SOFT_START_ALL_OFF   =  CT2_LO12BITS_OFF
CT2_SOFT_STOP_ALL_MSK    =  CT2_HI12BITS_MSK
CT2_SOFT_STOP_ALL_OFF    =  CT2_HI12BITS_OFF
def CT2_SOFT_START(reg,ctn):
    return BIT_SETB(reg,ctn)
def CT2_SOFT_STOP(reg,ctn):
    return BIT_SETB(reg,ctn+16)

#----------------------------------------------------------------------------
# Definitions for SOFT_LATCH register (W)
# reg = value of soft_latch register, ctn = [0,11] = counter number
#----------------------------------------------------------------------------
# used bits mask
CT2_SOFT_LATCH_UMSK    = CT2_LO12BITS_MSK
CT2_SOFT_LATCH_ALL_MSK = CT2_LO12BITS_MSK
CT2_SOFT_LATCH_ALL_OFF = CT2_LO12BITS_OFF
def CT2_SOFT_LATCH(reg,ctn):
    return BIT_SETB(reg,ctn)


# XXX

#CT2_NREGS_SOURCE_IT     =            (ct2_reg_size(1, source_it))
#CT2_NREGS_RD_CMPT       =            (ct2_reg_size(1, rd_cmpt))
#CT2_NREGS_RD_LATCH_CMPT =            (ct2_reg_size(1, rd_latch_cmpt))

#CT2_NREGS_SEL_FILTRE_INPUT =         (ct2_reg_size(2, sel_filtre_input))
#CT2_NREGS_SEL_FILTRE_OUTPUT_C208 =   (ct2_reg_size(2, c208_sel_filtre_output))
#CT2_NREGS_SEL_FILTRE_OUTPUT_P201 =   (ct2_reg_size(2, p201_sel_filtre_output))
#CT2_NREGS_SEL_SOURCE_OUTPUT_C208 =   (ct2_reg_size(2, c208_sel_source_output))
#CT2_NREGS_SEL_SOURCE_OUTPUT_P201 =   (ct2_reg_size(2, p201_sel_source_output))
#CT2_NREGS_SEL_LATCH =                (ct2_reg_size(2, sel_latch))
#CT2_NREGS_CONF_CMPT =                (ct2_reg_size(2, conf_cmpt))
#CT2_NREGS_COMPARE_CMPT =             (ct2_reg_size(2, compare_cmpt))



RD_CTRL_CMPT = 7
CT2_IOC_MAGIC = ord("w")

CT2_IOC_QXA = _IO(CT2_IOC_MAGIC, 21), \
    {errno.EACCES: "Failed to request exclusive access: no permission"}
CT2_IOC_LXA = _IO(CT2_IOC_MAGIC, 22), \
    {errno.EACCES: "Failed to relinquish exclusive access: no permission"}

CT2_IOC_DEVRST = _IO(CT2_IOC_MAGIC, 0), \
    {errno.EACCES: "Could not reset card: no permission"}


class BaseParam(object):
    """
    Base class for parameters
    """

    _FLAG_MAP = {}

    def __init__(self, value=None, **kwargs):
        self.__value = 0
        if value is None:
            self.set(**kwargs)
        else:
            if isinstance(value, self.__class__):
                value = value.value
            self.__value = value

    @property
    def value(self):
        """
        The parameter integer representation (R/W). To be interpreted as a 32bit unsigined integer

        It supports setting the value with either an integer or a dictionary
        """
        return self.__value

    @value.setter
    def value(self, config):
        if isinstance(config, dict):
            self.__value = 0
            self.set(**config)
        else:
            self.__value = config

    def set(self, **kwargs):
        """Sets/unsets the specified fields (convenience method)

        This is a convenience method for doing multiple ``param["<arg>"] = value``
        calls in one.

        The supported keywords are the same as returned by :meth:`keys`
        """
        for k, v in kwargs.items():
            self[k] = v

    def keys(self):
        """
        Returns the list of keys

        :return: the list of keys
        :rtype: list<str>
        """
        return self._FLAG_MAP.keys()

    def items(self):
        """
        Returns the list of parameter's (key, value) pairs, as 2-tuples

        :return: the list of parameter's (key, value) pairs, as 2-tuples
        :rtype: list<tuple(str, obj)>
        """
        return dict(self).items()

    def __getitem__(self, key):
        klass, mask = self._FLAG_MAP[key]
        return klass(self.value & mask)

    def __setitem__(self, key, value):
        klass, mask = self._FLAG_MAP[key]
        if not isinstance(value, klass):
            raise TypeError("{0} must be instance of {1}".format(key, klass.__name__ ))
        if value:
            self.value |= mask
        else:
            self.value &= NOT(mask)

    def __getattr__(self, name):
        return self[name]

    def __str__(self):
        pars = ", ".join(["{0}={1}".format(k, v) for k, v in self.items()])
        return "{0}({1})".format(self.__class__.__name__, pars)

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        if not isinstance(other, BaseParam):
            return False
        return self.__value == other.__value


class CtStatus(BaseParam):
    
    _FLAG_MAP = { 'enable': (bool, 1<< 0),
                  'run':    (bool, 1<< 16), }


class FilterOutput(BaseParam):

    _FLAG_MAP = { 'clock':    (FilterClock, 0b111),
                  'enable':   (bool, 1 << 3),
                  'polarity': (int,  1 << 4) }

    def __setitem__(self, key, value):
        if key == 'clock':
            klass, mask = self._FLAG_MAP[key]
            self.value = (self.value & NOT(mask)) | value.value


class AMCCFIFOStatus(BaseParam):
    """
    Card general status. Returned by :meth:`P201.get_general_status`
    """

    _FLAG_MAP = { 'read_empty': (bool, 1 << 0),
                  'write_full': (bool, 1 << 1),
                  'read_full':  (bool, 1 << 2),
                  'write_empty':(bool, 1 << 3), }


class FIFOStatus(BaseParam):

    _FLAG_MAP = { 'size':          (int,  0x1FFF),
                  'overrun_error': (bool, 1 << 16),
                  'read_error':    (bool, 1 << 17),
                  'write_error':   (bool, 1 << 18),
                  'empty':         (bool, 1 << 19),
                  'full':          (bool, 1 << 20), }

    def __setitem__(self, key, value):
        raise ValueError("FIFOStatus is read-only")


class CtConfig(BaseParam):
    """
    Counter configuration class

    To be used with methods :meth:`P201.get_counter_config` and
    :meth:`P201.get_counter_config`
    """

    _FLAG_MAP = { 'clock_source':              (CtClockSrc,     CT2_CONF_CMPT_CLK_MSK),
                  'gate_source':               (CtGateSrc,      CT2_CONF_CMPT_GATE_MSK),
                  'hard_start_source':         (CtHardStartSrc, CT2_CONF_CMPT_HSTART_MSK),
                  'hard_stop_source':          (CtHardStopSrc,  CT2_CONF_CMPT_HSTOP_MSK),
                  'reset_from_hard_soft_stop': (bool,           CT2_CONF_CMPT_RESET_MSK),
                  'stop_from_hard_stop':       (bool,           CT2_CONF_CMPT_STOP_MSK), }

    def __setitem__(self, key, value):
        klass, mask = self._FLAG_MAP[key]
        if not isinstance(value, klass):
            raise TypeError("{0} must be instance of {1}".format(key, klass.__name__ ))
        if key in ('reset_from_hard_soft_stop', 'stop_from_hard_stop'):
            super(CtConfig, self).__setitem__(key, value)
        else:
            self.value = (self.value & NOT(mask)) | value.value


class NiveauOut(BaseParam):
    
    _FLAG_MAP = { 'TTL': (bool, 1 << 8),
                  'NIM': (bool, 1 << 24) }


class TriggerInterrupt(BaseParam):

    _FLAG_MAP = { 'rising': (bool, 1 << 0),
                  'falling': (bool, 1 << 16) }


class P201:
    """
    P201 card class
    """

    #: list of valid card counters
    COUNTERS = range(1, 13)

    #: list of valid card channels
    CHANNELS = range(1, 11)

    #: list of valid card ouput channels
    OUTPUT_CHANNELS = 9, 10

    def __init__(self, name="/dev/p201"):
        self.__name = name
        self.__dev = open(name, "rwb+", 0)
        self.__log = logging.getLogger("P201." + name)

    def __ioctl(self, op):
        try:
            fcntl.ioctl(self.fileno, op[0])
        except (IOError, OSError) as exc:
            if exc.errno in op[1]:
                raise CT2Exception(op[1][exc.errno])
            else:
                raise

    @property
    def fileno(self):
        """
        internalcard file descriptor (don't use this member directly on your
        code)
        """
        return self.__dev.fileno()

    def request_exclusive_access(self):
        """
        Request exclusive access to the card. Nothing happens if the card
        has already exclusive access.

        :raises CT2Exception: if fails to get exclusive access
        """
        self.__ioctl(CT2_IOC_QXA)

    def relinquish_exclusive_access(self):
        """
        Relinquish exclusive access. Always succeeds.
        """
        self.__ioctl(CT2_IOC_LXA)

    def reset(self):
        """
        Resets the card.

        :raises CT2Exception: if fails to reset the card
        """
        self.__ioctl(CT2_IOC_DEVRST)

    def software_reset(self):
        """
        Does a software reset on the card.

        :raises OSError: in case the operation fails
        """
        self.write_reg("COM_GENE", 1 << 7)

    def _read_offset(self, offset):
        result = pread(self.fileno, offset)
        iresult = struct.unpack("I", result)[0]
        return iresult

    def _write_offset(self, offset, ivalue):
        """ """
        svalue = struct.pack("I", ivalue)
        return pwrite(self.fileno, svalue, offset)

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
        iresult = self._read_offset(offset)
        self.__log.debug("read %s (offset=%d) = %s", register_name,
                         offset, hex(iresult))
        return iresult

    def write_reg(self, register_name, ivalue):
        """
        Write from the specified register a given integer value. The value is interpreted
        as a 32bit unsigned integer

        **Low level call**.

        :param register_name: name of the register (case insensitive)
        :type register_name: str
        :param ivalue: value to write
        :type ivalue: int

        :raises OSError: in case the operation fails
        """
        register_name = register_name.upper()
        offset = CT2_R_DICT[register_name][0]
        self.__log.debug("write %s (offset=%d) with %s", register_name,
                         offset, hex(ivalue))
        return self._write_offset(offset, ivalue)

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
        return card_id, AMCCFIFOStatus(result)

    def get_niveau_out(self):
        """
        Returns the NIM/TTL level of all output channels (9 and 10)

        :return: the NIM/TTL level of all output channels (9 and 10)
        :rtype: dict<int: :class:`NiveauOut`>

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("NIVEAU_OUT")
        result, mask = {}, ((1 << 8) | (1 << 24))
        for i, channel in enumerate(self.OUTPUT_CHANNELS):
            reg = (register >> i) & mask
            result[channel] = NiveauOut(reg)
        return result

    def set_niveau_out(self, niveau_out):
        """
        Enables/disables output channels TLL and NIM.

        .. warning::
            non specified output channels will have their TTL and NIM set to disable

        :param niveau_out:
            dictionary where keys are output channel numbers and value is
            an instance of :class:`NiveauOut` representing the channel TTL and NIM
        :type niveau_out: dict<int: :class:`NiveauOut`>

        :raises OSError: in case the operation fails
        """
        register = 0
        for i, channel in enumerate(self.OUTPUT_CHANNELS):
            no = niveau_out.get(channel, NiveauOut())
            register |= (no.value) << i
        self.write_reg("NIVEAU_OUT", register)

    def get_output_channels_level(self):
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
            result[channel] = register & (1 << (channel-1)) != 0 and 1 or 0
        return result

    def set_output_channels_level(self, channels_output_level):
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
                register |= 1 << (channel-1)
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
            result[channel] = OutputSrc((register >> (n*8)) & 0xFF)
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
            register |= src.value << (n*8)
        self.write_reg("SEL_SOURCE_OUTPUT", register)

    def get_output_channels_filter(self):
        """
        Returns the current output channels filter configuration and polarity selection

        :return:
            dictionary where key is the channel number and value is the filter and
            polarity configuration (instance of :class:`FilterOutput`)
        :rtype: dict<int: class:`FilterOutput>`
        """
        result = {}
        register = self.read_reg("SEL_FILTRE_OUTPUT")
        for n, channel in enumerate(self.OUTPUT_CHANNELS):
            result[channel] = FilterOutput((register >> (n*8)) & 0xFF)
        return result

    def set_output_channels_filter(self, filter):
        """
        Sets the given ouput channels filter configuration and polarity selection

        :param filter: 
            dictionary where key is the channel number and value is the filter and
            polarity configuration (instance of :class:`FilterOutput`)
        :type filter: dict<int: class:`FilterOutput>`
        """
        register = 0
        for n, channel in enumerate(self.OUTPUT_CHANNELS):
            try:
                register |= filter[channel].value << (n*8)
            except KeyError:
                pass
        self.write_reg("SEL_FILTRE_OUTPUT", register)

    def get_DMA_enable_trigger_latch(self):
        """*not implemented*"""
        raise NotImplementedError

    def set_DMA_enable_trigger_latch(self, map):
        """*not implemented*"""
        raise NotImplementedError

    def get_FIFO_status(self):
        """
        Returns the current FIFO status

        :return: the card's current FIFO status
        :rtype: class:`FIFOStatus`
        """
        register = self.read_reg("CTRL_FIFO_DMA")
        return FIFOStatus(register)

    def get_channels_trigger_interrupts(self):
        """
        dict<int: :class:`TriggerInterrupt`>
        key: channel
        value: 
        """
        result = {}
        register = self.read_reg("SOURCE_IT_A")
        mask = (1<<0) | (1<<16)
        for channel in self.CHANNELS:
            reg = (register >> (channel-1)) & mask
            result[channel] = TriggerInterrupt(reg)
        return result

    def set_channels_trigger_interrupts(self, channels_triggers):
        """
        dict<int: class:`TriggerInterrupt`>
        key: channel
        value: 
        """
        register = 0
        for channel, triggers in channels_triggers.items():
            register |= triggers.value << (channel-1)
        self.write_reg("SOURCE_IT_A", register)

    def get_counters_trigger_interrupts(self):
        """*not implemented*"""
        raise NotImplementedError

    def set_counters_trigger_interrupts(self, counters_triggers):
        """*not implemented*"""
        raise NotImplementedError

    def get_trigger_interrupt_statuts(self):
        """*not implemented*"""
        raise NotImplementedError

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
        result, mask = {}, (1<<0) | (1<<16)
        for i, c in enumerate(self.COUNTERS):
            reg = (register >> i) & mask
            result[c] = CtStatus(reg)
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
        offset = CT2_R_DICT["RD_CMPT_1"][0] + (counter - 1)
        return self._read_offset(offset)

    def get_latch_value(self, latch):
        """
        Returns the current value of the given latch

        :param latch: latch number (starts with 1)
        :type latch: int
        :return: latch value
        :rtype: int

        :raises OSError: in case the operation fails
        """
        offset = CT2_R_DICT["RD_LATCH_CMPT_1"][0] + (latch - 1)
        return self._read_offset(offset)

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
        Sets the current configuration for the specified counter

        Example::

            >>> from bliss.controllers import ct2
            >>> p201 = ct2.P201()
            >>> print p201.get_counter_config()
            CtConfig(clock_source=CtClockSrc.CLK_100_MHz,
                     gate_source=CtGateSrc.GATE_CMPT,
                     hard_start_source=CtHardStartSrc.SOFTWARE_ONLY,
                     hard_stop_source=CtHardStopSrc.SOFTWARE_ONLY,
                     reset_from_hard_soft_stop=True,
                     stop_from_hard_stop=True)

        :param counter: counter number (starts with 1)
        :type counter: int
        :return: the current configuration for the specified counter
        :rtype: :class:`CtConfig`

        :raises OSError: in case the operation fails
        """
        register = self.read_reg("CONF_CMPT_{0}".format(counter))
        return CtConfig(register)

    def set_counter_config(self, counter, config):
        """
        Sets the current configuration for the specified counter

        *config* parameter can be an instance of :class:`CtConfig` or
        an integer representing the direct bit counter configuration.

        Example::

            from bliss.controllers.ct2 import P201, CtConfig

            config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                              gate_source=CtGateSrc.GATE_CMPT,
                              hard_start_source=CtHardStartSrc.SOFTWARE_ONLY,
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
        config = CtConfig(config)
        self.write_reg("CONF_CMPT_{0}".format(counter), config.value)

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
        for counter, config in counters_cfg.items():
            if isintance(config, dict):
                self.set_counter_config(counter, **config)
            else:
                self.set_counter_config(counter, value=config)

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
        c1, c2 = 2*latch_nb-1, 2*latch_nb

        register = self.read_reg("SEL_LATCH_" + latch)

        result = {c1: set(), c2: set()}
        for bit_nb, bit in enumerate(bin(register)[-1:1:-1], 1):
            if bit == '0':
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
        c1, c2 = 2*latch_nb-1, 2*latch_nb

        s1, s2 = counter_sources.get(c1, ()),counter_sources.get(c2, ())
        if isinstance(s1, int):
            s1 = s1,
        if isinstance(s2, int):
            s2 = s2,

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
        latch_str = "SEL_LATCH_" + (chr(((counter-1) % 12) // 2 + ord('A')))

        reg = (self.read_reg(latch_str) >> shift) & 0x0000FFFF

        return [ct for ct, bit in enumerate(bin(reg)[-1:1:-1], 1) if bit == '1']

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
        if isintance(counter_sources, int):
            counter_sources = counter_sources,

        # calculate which latch (A, B, ... F)
        latch_str = "SEL_LATCH_" + (chr(((counter-1) % 12) // 2 + ord('A')))

        # even counter will be represented in high 16 bits part
        if counter % 2:
            shift = 0
            mask  = 0xFFFF0000
        else:
            shift = 16
            mask  = 0x0000FFFF

        # read register so it can be *ored* with the new counter setting
        # because each register contains info about two counters.
        # (Example: SEL_LATCH_B contains config of counters 3 and 4
        sibling_source_bits = self.read_reg(latch_str) | mask

        # convert from list of counters to register bits
        source_bits = 0
        for source in counter_sources:
            source_bits |= 1 << (source - 1)
        source_bits = (source_bits << shift) | sibling_source_bits

        self.write_reg(latch, source_bits)

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

            p201.set_counters_latch_source({1 : 10,
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

        for counter, sources in counter_sources.items():
            if isinstance(sources, int):
                sources = sources,
            source_bits = 0
            for source in sources:
                source_bits |= 1 << (source - 1)

            # even counter will be represented in high 16 bits part
            shift = (counter % 2 == 0) and 16 or 0
            source_bits = source_bits << shift

            # calculate which latch (A, B, ... F)
            latch = chr(((counter-1) % 12) // 2 + ord('A'))
            register = latches[latch]
            latches[latch] = register | source_bits
        for latch, value in latches.items():
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
            latch_str = "SEL_LATCH_" + chr((latch-1) + ord('A'))
            register = self.read_reg(latch_str)
            c1, c2 = 2*latch-1, 2*latch
            for counter, bit in enumerate(bin(register)[-1:1:-1], 1):
                if bit == '0':
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

    def set_counter_comparator_value(self, counter, value):
        """
        Sets the given counter comparator value

        :param counter: counter number (starting at 1)
        :type counter: int
        :param value: comparator value
        :type value: int
        """
        self.write_reg("COMPARE_CMPT_%d" % counter, value)

    def get_50ohm_adapters(self):
        """
        Returns the enable/disable status of the channel 50 ohm adapter

        :return:
            a dictionary where key is the channel number (starting at 1)
            and value is bool (set to True if 50 ohm load is to be enabled,
            or False if it is to be disabled)
        :rtype: dict<int: bool>

        :raises OSError: in case the operation fails
        """
        result = {}
        for c in range(1, 10): result[c] = True

        register = self.read_reg("ADAPT_50") & P201_ADAPT_50_UMSK
        for input, bit in enumerate(bin(register)[-1:1:-1], 1):
            result[input] = bit == '0'
        return result

    def set_50ohm_adapters(self, inputs):
        """
        Enable/disable 50 ohm adapter from all channels.

        .. warning::
           non specified channels will be set as 50 ohm disabled

        :param inputs:
            a dictionary where key is the channel number (starting at 1)
            and value is bool (set to True to enable 50 ohm adapter, or False
            to disable it)
        :type inputs: dict<str: bool>

        :raises OSError: in case the operation fails
        """
        register = 0xFFFFFFFF
        for inp, value in inputs.items():
            if value:
                register &= NOT(1 << (inp-1))
        self.write_reg("ADAPT_50", register)

    def set_counters_software_start_stop(self, counters):
        """
        Software starts or stops the given counters.

        :param counters:
            dictionary where key is the counter number (starting at 1) 
            and value is bool (True means software start, False means software stop)
        :type counters: dict<int: bool>

        :raises OSError: in case the operation fails
        """
        register = 0
        for counter, action in counters.items():
            reg = 1 << (counter-1)
            if not action:
                reg = reg << 16
            register |= reg
        self.write_reg("SOFT_START_STOP", register)
    
    def set_counters_software_latch(self, counters):
        """
        Triggers a latch on the specified counters by software
        """
        register = 0
        for c in counters:
            register |= 1 << (c-1)
        self.write_reg("SOFT_LATCH", register)

    def set_counters_software_enable(self, counters):
        """
        Software enables/disables the given counters

        :param counters:
            dictionary where key is the counter number (starting at 1) 
            and value is bool (True means software enable, False means software disable)
        :type counters: dict<int: bool>

        :raises OSError: in case the operation fails
        """
        register = 0
        for counter, enable in counters.items():
            reg = 1 << (counter-1)
            if not enable:
                reg << 16
            register |= reg
        self.write_reg("SOFT_ENABLE_DISABLE", register)

    def enable_counters_software(self, counters):
        """
        Software enables the given counters

        This is a convenience method for :meth:`set_counters_software_enable`
        
        :param counters: 
            a container of the counters to be software enabled. It can be any python
            container of integers (tuple, list, iterable, even dict)
        :type counters: container<int>

        :raises OSError: in case the operation fails
        """
        ct = {}
        for counter in counters:
            ct[counter] = True
        self.set_counters_software_enable(ct)

    def disable_counters_software(self, counters):
        """
        Software disables the given counters

        This is a convenience method for :meth:`set_counters_software_enable`

        :param counters: 
            a container of the counters to be software disabled. It can be any python
            container of integers (tuple, list, iterable, even dict)
        :type counters: container<int>

        :raises OSError: in case the operation fails
        """
        ct = {}
        for counter in counters:
            ct[counter] = False
        self.set_counters_software_enable(ct)


def main():
    #logging.basicConfig(level=logging.DEBUG)

    def out(msg):
        sys.stdout.write(msg)
        sys.stdout.flush()

    p201 = P201()
    p201.request_exclusive_access()
    p201.reset()
    p201.software_reset()

    # internal clock 40 Mhz
    p201.set_clock(Clock.CLK_40_MHz)

    # channel 10 output: counter 10 gate envelop
    p201.set_niveau_out({10: NiveauOut(TTL=True)})

    # no 50 ohm adapter
    #p201.write_reg("ADAPT_50", 0x3FF)
    p201.set_50ohm_adapters({})

    # channel 9 and 10: no filter, no polarity
    #p201.write_reg("SEL_FILTRE_OUTPUT", 0)
    p201.set_output_channels_filter({})
    
    # channel 10 output: counter 10 gate envelop
    #p201.write_reg("SEL_SOURCE_OUTPUT", 0x70 << 8)
    p201.set_output_channels_source({10: OutputSrc.CT_10_GATE})

    # Internal clock to 1 Mhz [1us], Gate=1, Soft Start, HardStop on CMP,
    # Reset on Hard/SoftStop, Stop on HardStop
    #reg = 0x03 | (0 << 7) | (0 << 13) | (0x52 << 20) | (1 << 30) | (1 << 31)
    #p201.write_reg("CONF_CMPT_10", reg)
    ct10_config = CtConfig(clock_source=CtClockSrc.CLK_1_MHz,
                           gate_source=CtGateSrc.GATE_CMPT,
                           hard_start_source=CtHardStartSrc.SOFTWARE_ONLY,
                           hard_stop_source=CtHardStopSrc.CT_10_EQ_CMP_10,
                           reset_from_hard_soft_stop=True,
                           stop_from_hard_stop=True)
    p201.set_counter_config(10, ct10_config)

    # Latch on Counter 10 HardStop
    #p201.write_reg("SEL_LATCH_E", 0x200 << 16)
    p201.set_counters_latch_sources({10: 10})

    # Counter 10 will count 1 sec
    #p201.write_reg("COMPARE_CMPT_10", 1000*1000)
    p201.set_counter_comparator_value(10, 1000*1000)

    started, start_count = False, 0
    while not started:
        # SoftStart on Counter 10
        start_count += 1
        if start_count > 10:
            print("failed to start after 10 atempts" )
            break
        #p201.write_reg("SOFT_START_STOP", 0x200)
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

    #p201.write_reg("SOFT_ENABLE_DISABLE", 0x200 < 16)
    p201.disable_counters_software((10,))
    import pprint
    pprint.pprint(p201.get_counters_status())
    p201.relinquish_exclusive_access()
    return p201


if __name__ == "__main__":
    main()
