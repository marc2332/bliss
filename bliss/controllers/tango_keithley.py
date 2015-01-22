from bliss.common.task_utils import cleanup, error_cleanup, task
import PyTango.gevent

class tango_keithley:
   def __init__(self, name, config):
       self.name = name
       tango_uri = config["uri"]
       self.__control = PyTango.gevent.DeviceProxy(tango_uri)

   def read(self, acq_time=0):
     self.__control.MeasureSingle()
     self.__control.WaitAcq()
     return self.__control.ReadData

   def autorange(self, autorange_on=None):
     if autorange_on is None:
       return self.__control.autorange   
     else:
       self.__control.autorange = autorange_on

