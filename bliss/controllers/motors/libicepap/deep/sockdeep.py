# Standard modules
import socket
import string
import threading
import select
import os
import Queue
import pdb
import numpy

# DEEP modules
from . import log



# --------------------------------------------------------------------------
#

# Default socket port to use 
HOST_PORT   = 5000

# Default answer timeout in seconds
HOST_TIMEOUT= 1

# Asynchronous protocol
ASYNC_HEAD_ICESIGNATURE = 0xbebecafe
ASYNC_FRM_SHIFT         = 24

# Default verbose level
DEF_VERBOSE = log.DBG_NONE

# Used to end listening thread
exitFlag    = False



# --------------------------------------------------------------------------
#
class listenerThread(threading.Thread):

  # ------------------------------------------------------------------------
  #
  def __init__(self, host_socket, fifoin, piper):
    threading.Thread.__init__(self)
    self.host_socket = host_socket
    self.ready_event = threading.Event()
    self.inputs      = [host_socket, piper]
    self.outputs     = []
    self.fifoin      = fifoin
    self.piper       = piper
    self.daemon      = True


  # ------------------------------------------------------------------------
  #
  def run(self):
    async_head_mark = []
    c_cache         = []
    ASYNC_WLEN_MASK         = ((1<<ASYNC_FRM_SHIFT)-1)



    log.async("starting thread")  
    
    # return from time to time from the select to check exitFlag
    timeout = 1

    # convert asynchronous header in socket ordered bytes
    for idx in range(4):
      async_head_mark.append(chr((ASYNC_HEAD_ICESIGNATURE>>(8*idx)) & 0xff))
    idx = 0
    async_state = 0

    # inform main thread that we are about to start listening
    self.ready_event.set()

    # never ending loop until a sys.exit()
    while not exitFlag:

      # blocking call until there is something to read
      log.async("waiting for...")
      try:
        readable, writable, exceptional = \
          select.select(self.inputs, self.outputs, self.inputs, timeout)
      except KeyboardInterrupt:
        raise

      # ensure that there is something received
      if len(readable) == 0:
        continue

      # ensure that is not the pipe
      if self.piper in readable:
        continue

      # empty the socket receiving buffer
      log.async("something arrived...")
      try:
        ans = self.host_socket.recv(4096)

	# analyze each received byte looking for asynchronous transmition
        #
        # asynchronous binary data format:
        # 2 words startup mark 
        # 2 words for the binary data length + frame number << 24
        # 2 words for the checksum
        # n words of data
        #
	for c in ans:

          # look for async binary mark
          if async_state == 0:
	    if c == async_head_mark[idx]:
	      c_cache.append(c)
	      idx += 1
	      if idx < 4:
	        continue

              # found an async binary header mark
              log.async("startup mark found")
              async_state = 1
              idx = 0

              # missing async data, continue parsing
	      continue

          # look for async binary data length and checksum
          elif async_state == 1:
	    c_cache.append(c)
	    idx += 1
	    if idx < 8:
	      continue

            # found an async binary header
            async_header = numpy.fromstring(''.join(c_cache), numpy.uint32)
            async_blen   = (async_header[1] & ASYNC_WLEN_MASK) * 2

            log.async("header   field  : 0x%08x"%float(async_header[0]))
            log.async("data len field  : 0x%08x(words)"%float(async_blen/2))
            log.async("checksum field  : 0x%08x"%float(async_header[2]))
            log.async("frame number    : %d"%(async_header[1]>>ASYNC_FRM_SHIFT))
            async_state = 2
            idx = 0

            # missing async data, continue parsing
	    continue

          # wait for async binary data 
          # TODO: implement a sort of timeout
          elif async_state == 2:
	    c_cache.append(c)
	    idx += 1
	    if idx < async_blen:
	      continue

            # all async binary data received
            log.async("all data arrived: 0x%08x(bytes)"%len(c_cache))

            # end of asynchronous reception
            # TODO: inform registered clients
            async_state = 0
            idx = 0
            del c_cache[:] 

            # restart parsing
	    continue

          # at this point there is no async data
          # do not loose bytes that looked like async binary header
	  if(len(c_cache)):
	    for cc in c_cache:
              self.fifoin.put(cc)
            del c_cache[:] 

          # sync byte received to be delivered to main thread
          self.fifoin.put(c)
      
      except socket.timeout:
        continue
      except KeyboardInterrupt:
        raise

    # abnormal end of the thread
    log.async("finishing thread")






# --------------------------------------------------------------------------
#
class SockDeep:

  # ------------------------------------------------------------------------
  #
  def __init__(self, host, verbose = DEF_VERBOSE, timeout=None):
    global exitFlag

    try:
      # allow to specify a different port
      h,p = host.split(":")
    except:
      # othwerwise use the default port
      h = host
      p = HOST_PORT

    # get options 
    self.set_verbose(verbose)

    # at this point we should have every thing we need
    self.host_name  = h
    self.host_port  = int(p)
    msg = "object created, host: \"%s:%d\""% \
        (self.host_name, self.host_port)
    log.trace(msg)

    # open a socket connection
    self.host_socket=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # set socket answer timeout
    if timeout == None:
      timeout = HOST_TIMEOUT
    self.set_timeout(default = timeout)

    # try to connect to the device
    try:
      self.host_socket.connect((self.host_name,self.host_port))
    except:
      msg = "unable to connect to host: \"%s:%d\""% \
        (self.host_name,self.host_port)
      log.error(msg, exception=NetworkError)

    # prepare a FIFO to communicate with the listening thread
    self.fifoin = Queue.Queue()
    self.piper, self.pipew = os.pipe()
 
    # launch the listening thread
    exitFlag      = False
    self.listener = listenerThread(self.host_socket, self.fifoin, self.piper)
    self.listener.start()
    self.listener.ready_event.wait()
    log.trace("Thread running")  



  # ------------------------------------------------------------------------
  #
  def close(self):
    global exitFlag

    log.trace("close requested")  

    # inform the listening thread that the show is ending
    exitFlag = True

    # wake up listening thread
    os.write(self.pipew, "That's the end")

    # wait for the end of the thread
    self.listener.join()

    log.trace("close finished")  




  # ------------------------------------------------------------------------
  #
  def set_timeout(self, timeout = None, default = None):
    if default != None:
       self.host_timeout = default

    if timeout == None:
       timeout = self.host_timeout

    # the socket timeout is handled by the listening thread
    #self.host_socket.settimeout(timeout)


  # ------------------------------------------------------------------------
  #
  def puts(self, cmd):
    try:
      self.host_socket.sendall(cmd)
    except:
      msg = "error sending string to host: \"%s\""% (self.host_name)
      log.error(msg, exception=NetworkError)



  # ------------------------------------------------------------------------
  #
  def putchar(self,cmd):
    try:
      self.host_socket.sendall(cmd[0])
    except:
      msg = "error sending char to host: \"%s\""% (self.host_name)
      log.error(msg, exception=NetworkError)



  # ------------------------------------------------------------------------
  #
  def getchar(self, size = 1, ignoretimeout = False):
    try:
      # read 'size' characters from the socket
      ans = ""
      while len(ans) < size:
          ans += self.fifoin.get(1)
    except Queue.Empty:
      if ignoretimeout:
         return ""
      else:
         msg = "timeout reading char from host: \"%s\""% (self.host_name)
         log.error(msg, exception=NetworkError)
    except Exception as e:
      print e
      msg = "error reading char from host: \"%s\""% (self.host_name)
      log.error(msg, exception=NetworkError)

    # normal end
    if size == 1:
        log.data("rd: %s"%self.chardump(ans))
    return ans



  # ------------------------------------------------------------------------
  # A very dirty way of flushing the socket connection
  #
  def flush(self):
    #print "flushing..."
    self.host_socket.sendall("#\n")
    # the socket timeout is handled by the listening thread
    #self.host_socket.settimeout(0.2)
    try:
      while True:
        if self.getchar() == "":
          break
    except:
      pass
    # the socket timeout is handled by the listening thread
    #self.host_socket.settimeout(self.host_timeout)


  # ------------------------------------------------------------------------
  #
  def chardump(self,c):
   if   ord(c) == 0x0d:
    s="\\r"
   elif ord(c) == 0x0a:
    s="\\n"
   elif c in string.printable:
    s=c
   else:
    s=""
   
   return("(0x%02x) %s"%(ord(c),s))



  # ------------------------------------------------------------------------
  #
  def set_verbose(self, verb):
    log.trace("set_verbose called")
    log.level(verb)


  # ------------------------------------------------------------------------
  #
  def get_verbose(self):
    log.trace("get_verbose called")
    return(log.level())


  # ------------------------------------------------------------------------
  #
  def __del__(self):
    log.trace("object deleted, host  : \"%s\""%self.host_name)
    #self.listener.host_socket.close()
    




# --------------------------------------------------------------------------
#
class NetworkError(IOError):
  pass
