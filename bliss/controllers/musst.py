from bliss.comm import gpib
import numpy
import os
import struct
import itertools
import gevent.lock

def grouped(iterable, n):
    "s -> (s0,s1,s2,...sn-1), (sn,sn+1,sn+2,...s2n-1), (s2n,s2n+1,s2n+2,...s3n-1), ..."
    return itertools.izip(*[iter(iterable)]*n)

class musst:
   def __init__(self, name, config):
       self.gpib_ip = config["gpib"]
       self.gpib_pad = config["address"]
       self.gpib_device = None
       try:
           self.prg_root = config["musst_prg_root"]
       except:
           self.prg_root = None
       self.lock = gevent.lock.Semaphore()

   def putget(self, comm, ack=False):
     if self.gpib_device is None:
         self.connect()

     with self.lock:
       comm = comm if comm.endswith('\n') else comm+'\n'
       if comm.startswith("?"):
         ack = False
       if ack:
         comm = "#"+comm if not comm.startswith('#') else comm
       ret = self.gpib_device.write_read(comm, size=64*1024)
       if ret.endswith('\n'):
         ret=ret[:-1]
       if ret == "$":
         ret = ""
         while True:
           data = self.gpib_device.read(size=64*1024)
           if data.startswith('$'):
             break
           ret += data 
       if ack:
         return ret=="OK"
       try:
         return int(ret)
       except:
         if ret=="ERROR":
           raise RuntimeError("%s: %s" % (comm.strip(), self.putget("?ERR")))
         return ret

   def connect(self, timeout=3):
       with self.lock:
         self.gpib_device = gpib.Gpib(self.gpib_ip, pad=self.gpib_pad)
       #assert(self.putget("?VER")=='MUSST 01.00a')

   def upload_file(self, fname, prg_root=None):
       if prg_root:
           oscil_program = open(os.path.join(prg_root, fname))
       else:
           oscil_program = fname

       self.upload_program(oscil_program.read())

   def upload_program(self, program_data):
       self.putget("#CLEAR")
       program_lines = program_data.split("\n")
       formatted_prog= "".join(["+%s\n" % l for l in program_lines])
       with self.lock:
           self.gpib_device.write(formatted_prog)
       state = self.putget("?STATE")
       if state != "IDLE":
         raise RuntimeError(state)
       return True
       #return self.putget("?list err")==""

   def print_info(self):
       print self.putget("?INFO")

   def val(self, channel, value=None):
       return self.putget("?VAL %s" % channel)

   def io(self, channel, value=None):
       return self.putget("?IO %s" % channel)

   def get_data(self, nlines, npts, buf=0):
       values = []
       offset = 0

       # get data by chunks of 1024 values (= 4096 bytes)
       raw_values = []
       for i in xrange((nlines*npts)/1024):
         raw_values.append(self.putget("?*EDAT %d %d %d" % (1024, buf, offset)))
         offset += 1024
       remaining_data = (nlines*npts) % 1024
       #import pdb;pdb.set_trace()
       if remaining_data:
         #print "?*EDAT %d %d %d" % (remaining_data, buf, offset)
         raw_values.append(self.putget("?*EDAT %d %d %d" % (remaining_data, buf, offset)))
  
       data = numpy.fromstring("".join(raw_values), numpy.int32)
       data.shape = (nlines, npts)
       return data
