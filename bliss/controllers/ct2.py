import os
import sys
import errno
import fcntl
import ctypes
import ctypes.util
import struct
import logging


# low level pread and pwrite calls for the p201/c208 driver.

# even if we are using python >=  3.3 we cannot use os.pread/pwrite calls
# because of the semantics of the p201/c208 driver. For example, the read
# returns the number of adjacent registers that we actually read instead
# of the the number of bytes read like the linux programmer's manual specifies

__libc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('c'))

def pread(fd, buffersize, offset):
    buff = ctypes.create_string_buffer(buffersize)
    n = __libc.pread(fd, buff, buffersize, offset)
    err = ctypes.get_errno()
    if err != 0:
        ctypes.set_errno(0)
        raise OSError("pread error: %s (%d): %s" % (errno.errorcode(err), err, 
                                                    errno.strerror(err)))
    return buff[:]

def pwrite(fd, buff, offset):
    __libc.pwrite(fd, buff, len(buff), offset)
    err = ctypes.get_errno()
    if err != 0:
        ctypes.set_errno(0)
        raise OSError("pwrite error: %s (%d): %s" % (errno.errorcode(err), err, 
                                                     errno.strerror(err)))

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
[0x00, "SEL_FILTRE_INPUT_A", True, True, "Input 1to 6: filter configuration and deglitcher enable"],
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
CT2_COM_GENE_ENAB_OSC   = 0x00000010 # en(1)/dis(0)able oscillator
CT2_COM_GENE_SOFT_RESET = 0x00000080 # soft reset(1)
CT2_COM_GENE_FREQ_MSK   = 0x0000000f # Frequency bitmask
CT2_COM_GENE_FREQ_OFF   = 0          # Frequency offset

def ct2_clock_freq_ctor(a, b, c, d, e):
    return (((a) << 4)|((b) << 3)|((c) << 2)|((d) << 1)|((e) << 0))

CT2_COM_GENE_CLOCK_DISABLED     = ct2_clock_freq_ctor(0,  0, 0, 0, 0)

CT2_COM_GENE_CLOCK_AT_20_MHz    = ct2_clock_freq_ctor(1,  0, 1, 0, 1)
CT2_COM_GENE_CLOCK_AT_25_MHz    = ct2_clock_freq_ctor(1,  0, 1, 0, 0)
CT2_COM_GENE_CLOCK_AT_30_MHz    = ct2_clock_freq_ctor(1,  0, 0, 1, 0)
CT2_COM_GENE_CLOCK_AT_33_33_MHz = ct2_clock_freq_ctor(1,  0, 0, 0, 1)
CT2_COM_GENE_CLOCK_AT_40_MHz    = ct2_clock_freq_ctor(1,  1, 1, 1, 1)
CT2_COM_GENE_CLOCK_AT_45_MHz    = ct2_clock_freq_ctor(1,  1, 1, 0, 1)
CT2_COM_GENE_CLOCK_AT_50_MHz    = ct2_clock_freq_ctor(1,  1, 1, 0, 0)
CT2_COM_GENE_CLOCK_AT_60_MHz    = ct2_clock_freq_ctor(1,  1, 0, 1, 0)
CT2_COM_GENE_CLOCK_AT_66_66_MHz = ct2_clock_freq_ctor(1,  1, 0, 0, 1)
CT2_COM_GENE_CLOCK_AT_70_MHz    = ct2_clock_freq_ctor(1,  0, 1, 1, 0)
CT2_COM_GENE_CLOCK_AT_75_MHz    = ct2_clock_freq_ctor(1,  1, 0, 0, 0)
CT2_COM_GENE_CLOCK_AT_80_MHz    = ct2_clock_freq_ctor(1,  0, 1, 1, 1)
CT2_COM_GENE_CLOCK_AT_90_MHz    = ct2_clock_freq_ctor(1,  1, 1, 1, 0)
CT2_COM_GENE_CLOCK_AT_100_MHz   = ct2_clock_freq_ctor(1,  0, 0, 0, 0)

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


#----------------------------------------------------------------------------
# Definitions for SEL_SOURCE_OUTPUT_A/B/C (output source select) regs (R/W)
# For P201 only the last (= the 3rd) output source reg. is used
#----------------------------------------------------------------------------
C208_SOURCE_OUTPUT_UMSK = 0x7f7f7f7f  # used bits mask
P201_SOURCE_OUTPUT_UMSK = 0x00007f7f  # used bits mask

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
CT2_CONF_CMPT_CLEAR_BIT   =  30
CT2_CONF_CMPT_STOP_BIT    =  31

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

    

class P201:
    
    def __init__(self, name="/dev/p201"):
        self.__name = name
        self.__dev = open(name, "rw")
        self.__log = logging.getLogger("P201./dev/p201")

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
        return self.__dev.fileno()

    def request_exclusive_access(self):
        """Request exclusive access for the open file description in the call."""
        self.__ioctl(CT2_IOC_QXA)

    def relinquish_exclusive_access(self):
        """Request exclusive access for the open file description in the call."""
        self.__ioctl(CT2_IOC_LXA)

    def reset(self):
        self.__ioctl(CT2_IOC_DEVRST)        
                
    def read_reg(self, register_name):
        """read from the specified register and return a 32bit integer"""
        offset = CT2_R_DICT[register_name][0]
        result = pread(self.fileno, 4, offset)
        iresult = struct.unpack("I", result)[0]
        self.__log.debug("read %s (offset=%d) = %s", register_name, 
                         offset, hex(iresult))
        return iresult

    def write_reg(self, register_name, ivalue):
        """ """
        svalue = struct.pack("I", ivalue)
        offset = CT2_R_DICT[register_name][0]
        self.__log.debug("write %s (offset=%d) with %s", register_name, 
                         offset, hex(ivalue))
        return pwrite(self.fileno, svalue, offset)


    def set_niveau_out(self, ttl_out_9=False, ttl_out_10=False,
                       nim_out_9=False, nim_out_10=False):
        value = 0
        if ttl_out_9:  value |= P201_OUT_9_TTL_ENABLE
        if ttl_out_10: value |= P201_OUT_10_TTL_ENABLE
        if nim_out_9:  value |= P201_OUT_9_NIM_ENABLE
        if nim_out_10: value |= P201_OUT_10_NIM_ENABLE
        self.write_reg("NIVEAU_OUT", value)

    def get_niveau_out(self):
        result, value = {}, self.read_reg("NIVEAU_OUT")
        result["ttl_out_9"] =  bool(value & P201_OUT_9_TTL_ENABLE)
        result["ttl_out_10"] = bool(value & P201_OUT_10_TTL_ENABLE)
        result["nim_out_9"] =  bool(value & P201_OUT_9_NIM_ENABLE)
        result["nim_out_10"] = bool(value & P201_OUT_10_NIM_ENABLE)
        return result

    def set_clock(self, clock):
        self.write_reg("COM_GENE", clock)        

    def read_ctrl_cmpt(self):
        return self.read_reg("RD_CTRL_CMPT")

    def set_clock(self, clock):
        self.write_reg("COM_GENE", clock)

    def read_test_reg(self):
        return self.read_reg("TEST_REG")

    def read_cmpt_10(self):
        return self.read_reg("RD_CMPT_10")

    def read_latch_10(self):
        return self.read_reg("RD_LATCH_CMPT_10")

    
def main():
    logging.basicConfig(level=logging.DEBUG)
    p201 = P201()
    
    p201.request_exclusive_access()
    p201.reset()

    # internal clock 40 Mhz
    p201.set_clock(CT2_COM_GENE_CLOCK_AT_40_MHz)

    # channel 10 output: counter 10 gate envelop
    p201.set_niveau_out(ttl_out_10=True)

    # no 50 ohm adapter
    p201.write_reg("ADAPT_50", 0x3FF)

    # channel 9 and 10: no filter, no polarity
    p201.write_reg("SEL_FILTRE_OUTPUT", 0) 

    # channel 10 output: counter 10 gate envelop
    p201.write_reg("SEL_SOURCE_OUTPUT", 0x70 << 8)

    # Internal clock to 1 Mhz [1us], Gate=1, Soft Start, HardStop on CMP, 
    # Reset on Hard/SoftStop, Stop on HardStop
    reg = 0x03 | (0 << 7) | (0 << 13) | (0x52 << 20) | (1 << 30) | (1 << 31)
    p201.write_reg("CONF_CMPT_10", reg)

    # Latch on Counter 10 HardStop
    p201.write_reg("SEL_LATCH_E", 0x200 << 16)

    # Counter 10 will count 1 sec
    p201.write_reg("COMPARE_CMPT_10", 1000*1000)

    start, start_count = False, 0
    while not start:
        # SoftStart on Counter 10
        start_count += 1
        if start_count > 10:
            print "failed to start after 10 atempts" 
            break
        p201.write_reg("SOFT_START_STOP", 0x200)
        status = p201.read_ctrl_cmpt()
        if status & (0x200 << 16) != 0:
            start = True
    
    if start:
        while True:
            counter = p201.read_cmpt_10()
            latch = p201.read_latch_10()
            status = p201.read_ctrl_cmpt_10()
            print counter, latch, status
            if status & (0x200 << 16) != 0:
                break

    p201.relinquish_exclusive_access()
    return p201


if __name__ == "__main__":
    main()
