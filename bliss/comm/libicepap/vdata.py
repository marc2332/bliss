"""IcePAP library"""


#-------------------------------------------------------------------------
# Standard modules
#
import string
import struct
import numpy


#-------------------------------------------------------------------------
# Library modules
#
from ..libdeep import log 


#-------------------------------------------------------------------------
# Global definitions 
#
PARAMETER = 'P'
POSITION  = 'A'
SLOPE     = 'S'

BYTE      = 'BYTE'
WORD      = 'WORD'
DWORD     = 'DWORD'
LWORD     = 'LWORD'
FLOAT     = 'FLOAT'
DFLOAT    = 'DFLOAT'
UBYTE     = 'UBYTE'
UWORD     = 'UWORD'
UDWORD    = 'UDWORD'
ULWORD    = 'ULWORD'

ADDRUNSET = 0xFF




#-------------------------------------------------------------------------
# Class definition
#
class vdata(object):
    """IcePAP data vector

    # object creation
    v = vdata()

    # appending data
    data = list(...)
    addr = 3
    type = vdata.PARAMETER  | POSITION | SLOPE
    v.append(data, addr, type)
    v.append(data, addr, type, format=vdata.DWORD)
    v.append(data, addr, type, incremental=True)

    """

    """Private menbers"""
    __signature   = 0xCAFE
    __incremental = 0x8000

    __type_code = {
        PARAMETER:0x1000,
        POSITION :0x2000,
        SLOPE    :0x4000
    }

    __type_desc = {
        PARAMETER:'PARAMETER',
        POSITION :'POSITION',
        SLOPE    :'SLOPE'

    }
    
        
    __format_code = {
        BYTE    :0x00,
        WORD    :0x01,
        DWORD   :0x02,
        LWORD   :0x03,
        FLOAT   :0x04,
        DFLOAT  :0x05,
        UBYTE   :0x10, 
        UWORD   :0x11,
        UDWORD  :0x12,
        ULWORD  :0x13
    }

    __format_dtype = {
        BYTE    :'b',
        WORD    :'h', 
        DWORD   :'l',
        LWORD   :'q',
        FLOAT   :'f',
        DFLOAT  :'d',
        UBYTE   :'B',
        UWORD   :'H',
        UDWORD  :'L',
        ULWORD  :'Q'
    }
            
    __header_format = '<HBBLLBBHd'
    """
    from DSP source code:
    typedef struct {
     uint16_t    signature;   // Signature must be VDAT_SIGNATURE (0xCAFE)
     uint16_t    offset_vers; // High byte: data offset in dwords = 6  (0x0018)
                              // Low byte: version of the data vector format (0)
     uint32_t    v_size;      // full vector size in dwords 
     uint32_t    n_values;    // number of values in the vector
     uint16_t    compr_dtype; // high byte: compression algorithm: 
                              //            0=uncompressed, 1=lzapp 
                              // low byte:  data type
     uint16_t    flags_addr;  // coding flags and board address 
     extdfloat_t firstvalue;  // first vector value if incremental 
    } vdatheader_t;
    """

    def __init__(self):
        """Object constructor"""
        self._bytearray = bytearray(0)


    def append(self, data, addr, type, format=DWORD, incremental=False):
        """Append data to current"""

        # Minimum checks
        if((addr < 0) or (addr > 255)):
            raise ValueError("invalid address, must be [0:255]")

        if(len(data) > 0xFFFF):
            raise ValueError("too many data values, max: 0xFFFF")

        if(type not in self.__type_code):
            raise ValueError("invalid type specified")

        if(format not in self.__format_code):
            raise ValueError("invalid format specified")

        #
        dtype = self.__format_code[format]
        flags = self.__type_code[type] + addr

        dformat = '<' + str(len(data)) + self.__format_dtype[format]

        if incremental:
            firstval = data[0]
            data = [0 if i == 0 else \
                data[i]-data[i-1] for i in range(len(data))]
            flags |= self.__incremental
        else:
            firstval = 0

        header_size = struct.calcsize(self.__header_format)
        full_size = header_size + struct.calcsize(dformat)
        if full_size % 4: full_size += 4 - (full_size % 4)

        #print("header_size", header_size)
        #print("full_size", full_size)
        #print("data format", dformat)

        # build the byte array
        bin_column = bytearray(full_size)
        struct.pack_into(self.__header_format, bin_column, 0,
            self.__signature,  # vdata signature
            0,                 # Version = 0
            header_size / 4,   # Data offset in dwords
            full_size / 4,     # Full vector size in dwords
            len(data),         # number of values in the vector
            dtype,             # Data type 
            0,                 # no compression
            flags,             # format + address
            firstval           # first data value for incremental coding
            )
        struct.pack_into(dformat, bin_column, header_size, *data)

        # append the byte array
        self._bytearray += bin_column


    def bin(self):
        """Return an IcePAP binary compatible block"""
        return numpy.array(self._bytearray, dtype=numpy.int8)


    def type_to_str(self, flags):
        """Returns a string describing an encoded vector type"""
        flags &= 0xff00
        for type in self.__type_code:
            if flags == self.__type_code[type]:
                return self.__type_desc[type]
        return 'unknown'


    def addr_to_str(self, flags):
        """Returns the destination address from an encoded vector header"""
        return flags & 0xff


    def loginfo(self):
        """Print out on log information about the data vector"""

        # brute dump of bytes
        # TODO: replace the test by a log.istrace()
        if log.level() >= log.DBG_DATA:
            log.trace("data vector contains:")
            n = self.bin()
            print ' '.join('0x{0:02x}'.format(x & 0xff) for x in n)

        # minimum check
        header_size = struct.calcsize(self.__header_format)
        if len(self._bytearray) < header_size:
            return

        # loop over all slices of data vector
        idx = 0
        cpt = 1
        while len(self._bytearray[idx:]) >= header_size:

            # extract header information
            (
                signature, version, header_sz, full_sz, 
                data_len, data_type, compression,    
                flags, firstval
            ) = struct.unpack_from(
                self.__header_format, 
                bytes(self._bytearray[idx:]))

            # minium check
            if signature != self.__signature:
                raise ValueError('corrupted data vector, missing signature')

            # convert size from DWORD to bytes
            full_sz *= 4 

            #
            log.trace("#%d: data vector type: %s" % 
                (cpt, self.type_to_str(flags)))
            log.trace("#%d: destination addr: %d" % 
                (cpt, self.addr_to_str(flags)))
            log.trace("#%d: number of data  : %d" % 
                (cpt, data_len))
            log.trace("#%d: data vector size: %dbytes" % 
                (cpt, full_sz))

            # jump to next slice
            idx += full_sz
            cpt += 1
