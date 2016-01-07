
"""Handle communication with any Deep or IcePAP device"""

# Standard modules
import string
import time
import numpy
import sys
import pdb
from threading import Lock #import gevent

# DEEP modules
from . import log 

# Get python modules to communicate with an DEEP device
from sockdeep import SockDeep
from sldeep import SLDeep





# End of Command character and other special ones
COMM_EOL    = "\n"
COMM_ACK    = "#"
COMM_REQ    = "?"
COMM_ADR    = ":"
COMM_BIN    = "*"
COMM_MLI    = "$"

# Device long answer timeout in seconds
COMM_LONG_TIMEOUT = 20

# Device generic command
COMM_ALIVE_CMD    = "?PING"
COMM_ALIVE_ICECMD = "?_SOCKPING"
COMM_ALIVE_ANS    = "OK"

# Binary protocol
BIN_HEAD_SIGNATURE     = 0xa5a50000
BIN_HEAD_ICESIGNATURE  = 0xa5aa555a
BIN_HEAD_SIGNMASK      = 0xffff0000
BIN_HEAD_NOCHECKSUM    = 0x00000010
BIN_HEAD_BIG_ENDIAN    = 0x00000020
BIN_HEAD_UNITMASK      = 0x0000000f

# Binary value type given in bytes per single value
BIN_8  = 1        
BIN_16 = 2
BIN_32 = 4
BIN_64 = 8


#
#
#
class DeviceError(Exception):

  #
  #
  def __init__(self, device, message):
	  Exception.__init__(self, device.hostname() + ': ' + message) 







#
#
#
class DeepDevice(object):

  _icepapmode = False


  #
  #
  def __init__(self, dev, argin_str="", timeout=None):

    # parse options given at object creation
    argins = string.split(argin_str)
    for argin in argins:
      try:
        opt,val = string.split(argin,"=")
      except:
        self._syntax_error("invalid option: \"%s\""%argin)

      opt=string.lower(opt)


      if opt.startswith("mode"):
        if val.lower() == "icepap":
          self._icepapmode = True
        else: 
          self._syntax_error("invalid communication mode: \"%s\""%val)

      elif opt.startswith("verb"):
        self.set_verbose(int(val))

      else:
        self._syntax_error("unknown option: \"%s\""%argin)

    log.trace("object created, device: \"%s\""%dev)
    if self._icepapmode:
        log.trace("using IcePAP compatibility mode")

    self.set_debug_mode(False)

    # TODO: try to guess if it is an IP or an SL to avoid 
    # to create socket connection and getting socket timeout
    try:
      comm_dev = SockDeep(dev, log.level(), timeout)
    except:
      raise
      try:
        comm_dev = SLDeep(dev, log.level(), timeout)
      except:
        msg = "unsupported communication device (SL or socket): \"%s\""%dev
        log.error(msg, exception=IOError)

    self.comm_dev       = comm_dev
    self._hostname      = dev
    self._to_be_flushed = False

    try:
      self.commands = self._getcommandlist()
    except:
      raise
      msg = "Not active device: \"%s\""%dev
      log.error(msg, exception=IOError)


  #
  #
  def close(self):
    self.comm_dev.close()


  #
  #
  def set_debug_mode(self, dbgmode):
    self.debug_mode = bool(dbgmode)




  #
  #
  def set_verbose(self, val):
    log.level(val)

  #
  #
  def get_verbose(self):
    return(log.level())



  #
  #
  def log(self, msg, verb):
    log.log(verb, msg)


  #
  #
  def hostname(self):
    return(self._hostname)


  #
  #
  def _getcommandlist(self):
    if self._icepapmode:
       answ = self.command("?HELP").splitlines()
       answ = [s for line in answ for s in line.split()]
    else:
       answ = self.command("?HELP ALL").splitlines()
       answ = [s.split(":")[0].strip() for s in answ if s.rfind(":") >= 0]
    return answ

  #
  #
  def getcommandlist(self):
    return self.commands



  #
  #
  def isvalidcommand(self, comm):
    if comm.split()[0].upper() in self.commands:
      return True
    else:
      return False




  #
  # Log the error message and raises an exception
  #
  def _syntax_error(self, msg):
    log.error(msg, exception=SyntaxError)





  #
  # Command Syntax: [#][<address>:]<keyword> [param1 [param2] etc][\r]\n
  # Keyword Syntax: [?|*|?*]<string>
  #
  def __cmd_type(self, str_cmd, chkanswer):

    # will return a list
    cmd_type = []

    # consider only the command not its params
    cmd = str_cmd.split()[0].upper()

    # check if acknowledge is requested
    if cmd[0] == COMM_ACK:
      ack = True
      cmd = cmd.lstrip(COMM_ACK)
    else:
      ack = False
      
    # check for an address field
    spcmd = cmd.split(COMM_ADR)
    n = len(spcmd)
    if n == 1:
      cmd_addr = None
      prefix = spcmd[0]
    elif n == 2:
      cmd_addr = spcmd[0]
      prefix = spcmd[1]
    else:
      self._syntax_error("too many \"%s\" chars"%(COMM_ADR))

    if not prefix:              # missing keyword
      self._syntax_error("missing command keyword")
    elif prefix[0] == COMM_REQ:   # this is a query
      cmd_type.append("req")
      cmd_key = prefix[1:]
      if cmd_addr == "":        # if broadcast, error
        self._syntax_error("queries cannot be broadcasted")
      elif ack:                 # if acknowledge, cancel answer check
        chkanswer = False
      else:
        chkanswer = True
    else:
      cmd_key = prefix
      if ack:
        cmd_type.append("ack")
        
    # check if binary
    if cmd_key[0] == COMM_BIN:      # binary data
      cmd_type.append("bin")
      cmd_key = cmd_key[1:]

    # minimum check on characters for address and command fields
    if not cmd_key.replace("_", "").isalnum():
        self._syntax_error("invalid character in command %s"%(prefix))

    if cmd_addr and not cmd_addr.replace("_", "").isalnum():
        self._syntax_error("invalid character in address %s"%(cmd_addr))

    if cmd_addr and self._icepapmode:
        prefix = cmd_addr + COMM_ADR + prefix

    # normal end
    msg = "command: %s type: %s"%(prefix, cmd_type)
    log.data(msg)
    return prefix, cmd_type, chkanswer



  #
  #
  def __dump_bin(self, data):
    """Dump in hexa the values of the NumPy array of type from 8 to 64bit"""

    # give up if nothing to do
    if(log.level() < log.DBG_DATA):
       return

    # guess information on data to dump
    bufsize  = data.nbytes      # specfic to NumPy arrays
    datasize = len(data)        # number of values
    datatype = bufsize/datasize # number of bytes per individual value

    # minium check
    if datatype not in [BIN_8, BIN_16, BIN_32, BIN_64]:
       self._syntax_error("unsupported data type: BIN_%dbits"%(datatype*8))


    #
    print "  binary data: %d bytes"%bufsize
    lnv = 80 / (datatype*2 + 4)
    for j in range(1,datasize+1):
      if datatype == BIN_8:
        hexstr = "%02x"%(data[j-1] & 0xff)
      # NOTE MP 14Jun2013: problem with string formating in Python <=2.6.5
      # with integers larger than 32bit. Therefore handle them by hand
      if datatype >= BIN_16:
        hexstr = "%04x"%(data[j-1] & 0xffff)
      if datatype >= BIN_32:
        hexstr = "%04x"%((data[j-1]>>16) & 0xffff) + hexstr
      if datatype >= BIN_64:
        hexstr = "%04x"%((data[j-1]>>32) & 0xffff) + hexstr
        hexstr = "%04x"%((data[j-1]>>48) & 0xffff) + hexstr
  
      hexstr  = "  0x" + hexstr
      sys.stdout.write(hexstr)
      if not j%lnv:
        sys.stdout.write("\n")
  
    #
    sys.stdout.write("\n")
    sys.stdout.flush()





  #
  #
  def __wr(self, str_cmd, has_reply):
    if self._to_be_flushed:
      self.flush()

    cmd = str_cmd + "\n"

    # send the command passed as string
    log.trace("===> [%s]"%str_cmd)
    if has_reply:
        return self.comm_dev.request(cmd)
    else:
        self.comm_dev.puts(cmd)


  #
  #
  def __wr_bin(self, str_cmd, in_data):
    self.__wr(str_cmd)

    # prepare binary protocol header
    header    = numpy.array([0,0,0],numpy.uint32)
    if not self._icepapmode:
      header[0] = BIN_HEAD_SIGNATURE | (in_data.itemsize & BIN_HEAD_UNITMASK)
      header[1] = len(in_data)
      header[2] = numpy.uint32(numpy.sum(in_data))
    # for IcePAP the protocol is different 
    else:
      header[0] = BIN_HEAD_ICESIGNATURE 
      header[1] = in_data.nbytes/2        # data length given in 16bit words
      org_dtype = in_data.dtype
      in_data.dtype = numpy.uint16        # checksum calculate over 16bits words
      header[2] = numpy.uint32(numpy.sum(in_data))
      in_data.dtype = org_dtype           # avoid client panic

    # sent header (the float() is needed to handle the unsigned long)
    log.data("header   field: 0x%08x"%float(header[0]))
    log.data("data len field: 0x%08x"%float(header[1]))
    log.data("checksum field: 0x%08x"%float(header[2]))


    # header must be always sent as little-endian (mandatory)
    # binary data is convenient (and not to use the BIG_ENDIAN flag)
    if sys.byteorder == "big":
      #header[0] |= BIN_HEAD_BIG_ENDIAN
      header.byteswap(True)               # convert header in little endian
      bin_block = in_data.byteswap(False) # put data in little endian too
    else:
      bin_block = in_data

    # send the header and the binary block
    self.__dump_bin(bin_block)
    self.comm_dev.puts(header)
    self.comm_dev.puts(bin_block)




  # 
  #
  def __rd_bin(self):
  
    # load binary protocol header
    header = numpy.fromstring(self.comm_dev.getchar(3 * 4), numpy.uint32)
    if sys.byteorder == "big":
        header.byteswap(True)            # convert header from little endian

    # received header (the float() is needed to handle the unsigned long)
    log.data("header   field: 0x%08x"%float(header[0]))
    log.data("data len field: 0x%08x"%float(header[1]))
    log.data("checksum field: 0x%08x"%float(header[2]))


    # retrieve information from binary protocol header
    if not self._icepapmode:
      if (header[0] & BIN_HEAD_SIGNMASK) !=  BIN_HEAD_SIGNATURE:
        raise IOError, "bad binary data header"
      itemsize  = header[0] & BIN_HEAD_UNITMASK
      usechksum = not (header[0] & BIN_HEAD_NOCHECKSUM)
      bigendian = header[0] & BIN_HEAD_BIG_ENDIAN
    # for IcePAP the protocol is different 
    else:
      if header[0] !=  BIN_HEAD_ICESIGNATURE:
        raise IOError, "bad IcePAP binary data header"
      itemsize  = 2                      # only 16bit words can be transfert
      usechksum = True                   # checksum is mandatory
      bigendian = False

    size     = header[1]
    checksum = header[2]

    bin_block = numpy.fromstring(self.comm_dev.getchar(size * itemsize), \
      {1:numpy.uint8, 2:numpy.uint16, 4:numpy.uint32, 8:numpy.uint64}[itemsize])

    if (bigendian and sys.byteorder == "little") or \
       (not bigendian and sys.byteorder == "big"):
      bin_block.byteswap(True)         # convert data into native ordering

    #
    calc_checksum = long(bin_block.sum()) & 0xffffffff  # checksum to 32 bits
    if usechksum and calc_checksum != checksum:
        raise IOError, "Bad binary checksum"


    # for IcePAP force return data type to 8bits rather than 16bits which
    # is meaningless for the client
    if self._icepapmode:
      bin_block.dtype=numpy.uint8

    # normal end
    self.__dump_bin(bin_block)
    return bin_block


  #
  #


  #
  #
  def __command(self, str_cmd, in_data = None, chkanswer = False): #, lock=Lock()):

    # remove any useless ending white spaces and eols
    cmd = str_cmd.strip(" \n\r") 

    # some parsing to guess what to do
    prefix, cmd_type, chkanswer = self.__cmd_type(cmd, chkanswer)

    # by default no binary data returned
    ans_data = None

    if True:
              #     minimum check if binary download is requested
	    if in_data == None:
	      if "bin" in cmd_type and not "req" in cmd_type:
		self._syntax_error("binary data is missing")
	      else:
		reply = self.__wr(cmd, "req" in cmd_type or "ack" in cmd_type)
	    else:
	      if not "bin" in cmd_type:
		self._syntax_error("downloading binary with a non binary command")
	      elif "req" in cmd_type:
		self._syntax_error("downloading binary with a query binary command")
	      else:
		self.__wr_bin(cmd, in_data)
		if "ack" in cmd_type:
		  self.comm_dev.set_timeout(COMM_LONG_TIMEOUT)

	    if "req" in cmd_type or "ack" in cmd_type:
              try:
	          ans = reply.get() #self.__rd_ascii(prefix)
              except RuntimeError, msg:
	          if chkanswer:
		     raise DeviceError(self, msg)
              else: 
	          if "bin" in cmd_type:
		    if "req" in cmd_type:
		      ans_data = self.__rd_bin()
		      return ans, ans_data
		    else:
		      self.comm_dev.set_timeout()
		      return ans
	          else:
		    return ans

  #
  #
  def command(self, str_cmd, in_data = None):
    try:
      return self.__command(str_cmd, in_data, False)
    except IOError:
      self._to_be_flushed = True
      raise
    except KeyboardInterrupt:
      self._to_be_flushed = True
      if self.debug_mode:
          print "Keyboard interrupt"
      raise



  #
  #
  def ackcommand(self, str_cmd, in_data = None):
    str_cmd = str_cmd.strip()
    
    if str_cmd[0] != "#" and str_cmd[0] != "?":
      str_cmd = "#" + str_cmd
    try:
      return self.__command(str_cmd, in_data, True)
    except IOError:
      self._to_be_flushed = True
      raise
    except KeyboardInterrupt:
      self._to_be_flushed = True
      if self.debug_mode:
          print "Keyboard interrupt"
      raise
       



  #
  #
  def flush(self):
    if self.debug_mode:
      print "Flushing ..."
    self.comm_dev.flush()
    self._to_be_flushed = False



  #
  #
  def isalive(self):
   
    # by default, no body is there
    alive = False

    # try a generic command
    if self._icepapmode:
      cmd = COMM_ALIVE_ICECMD
    else:
      cmd = COMM_ALIVE_CMD

    try: 
      ans = self.command(cmd)
    except:
      self._syntax_error("isalive command \"%s\" failed"%cmd)
    
    # at this point we could consider a usable device but be paranoic
    if (string.find(ans,"OK") != -1):
      alive = True  

    # normal end
    return alive 







