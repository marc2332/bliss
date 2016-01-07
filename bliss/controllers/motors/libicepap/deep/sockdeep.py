# Standard modules
import socket
import string
import sys
import threading
if 'gevent' in sys.modules:
  from gevent import queue as Queue
  import gevent.event
else:
  import Queue
import select
import os
import pdb
import numpy
import itertools

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


class Reply:
  def __init__(self):
    self.queue = Queue.Queue()

  def put(self, *args, **kwargs):
    return self.queue.put(*args, **kwargs)

  def get(self, *args, **kwargs):
    try:
        ret, msg = self.queue.get(*args, **kwargs)
    except Queue.Empty:
          return None, None
    if ret == 'ERROR':
        raise RuntimeError(msg)
    return ret

# --------------------------------------------------------------------------
#
class BaseListenerThread:

  # ------------------------------------------------------------------------
  #
  def __init__(self, host_socket, replies_list, piper):
    self.host_socket = host_socket
    self.inputs      = [host_socket, piper]
    self.outputs     = []
    self.__replies   = replies_list
    self.incoming_data = ""
    self.piper       = piper


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

    multiline = False
    msg = ""

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
        ans = self.host_socket.recv(4096*4)

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
              self.incoming_data += cc
            del c_cache[:] 

          # sync byte received to be delivered to main thread
          self.incoming_data += c

          if self.incoming_data.endswith('\n'):
              raw_replies = self.incoming_data.split('\n')
              self.incoming_data = ""
              for raw_reply in raw_replies:
                  if raw_reply:
                      if raw_reply == '$':
                          multiline = False
                          ret = msg
                          msg = ""
                      else:
                          if multiline:
                              msg += raw_reply
                              continue
                          else:
                              reply_iterator = itertools.chain(raw_reply.split(" "))
                              read_cmd_str = reply_iterator.next()
                              if read_cmd_str.endswith('\n'):
                                  read_cmd_str = read_cmd_str[:-1]
                              ret = reply_iterator.next().strip('\r\n')
                              msg = " ".join(reply_iterator).strip('\n')
                               
                              if ret.endswith('$'):
                                  multiline = True
                                  continue
                    
                      reply = self.__replies.pop(0)
                      reply.put((ret, msg)) 
                      msg = ""
      except socket.timeout:
        continue

    # abnormal end of the thread
    log.async("finishing thread")


class GListenerThread(BaseListenerThread):
  def __init__(self, *args, **kwargs):
    BaseListenerThread.__init__(self, *args, **kwargs)
    self._thread = None
    self.ready_event = gevent.event.Event()

  def start(self):
    self._thread = gevent.spawn(self.run)

  def join(self):
    self._thread.join()


class listenerThread(threading.Thread, BaseListenerThread):
  def __init__(self, *args, **kwargs):
    threading.Thread.__init__(self)
    self.daemon = True
    self.ready_event = threading.Event()
    BaseListenerThread.__init__(self, *args, **kwargs)


if 'gevent' in sys.modules:
    listenerThread = GListenerThread


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
    self.__replies = list()
    self.piper, self.pipew = os.pipe()
 
    # launch the listening thread
    exitFlag      = False
    self.listener = listenerThread(self.host_socket, self.__replies, self.piper)
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
  def request(self, cmd):
      self.puts(cmd)
      reply = Reply()
      self.__replies.append(reply)
      return reply
      

  # ------------------------------------------------------------------------
  #
  def putchar(self,cmd):
    try:
      self.host_socket.sendall(cmd[0])
    except:
      msg = "error sending char to host: \"%s\""% (self.host_name)
      log.error(msg, exception=NetworkError)




  # ------------------------------------------------------------------------
  # A very dirty way of flushing the socket connection
  #
  def flush(self):
    #print "flushing..."
    r = self.request("#\n") #self.host_socket.sendall("#\n")
    r.get()


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


