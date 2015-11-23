from bliss.common.task_utils import *
from bliss.common import dispatcher
import PyTango.gevent

class tango_transfocator:
   def __init__(self, name, config):
      tango_uri = config.get("uri")
      self.__control = None
      try:
         self.__control = PyTango.gevent.DeviceProxy(tango_uri)
      except PyTango.DevFailed, traceback:
         last_error = traceback[-1]
         print "%s: %s"  % (tango_uri, last_error['desc'])
         self.__control = None
      else:
         try:
            self.__control.ping()
         except PyTango.ConnectionFailed:
            self.__control = None
            raise ConnectionError

   def status_read(self):
      return self.__control.ShowLenses
      
   def tfin(self, lense):
      self.__control.LenseIn(lense)

   def tfout(self, lense):
      self.__control.LenseOut(lense)

   def tfstatus_set(self, stat):
      self.__control.TfStatus = stat
