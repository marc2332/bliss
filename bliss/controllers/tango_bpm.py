from bliss.common.task_utils import *
import time
import PyTango.gevent

class Counter:
   def __init__(self, parent, name, index):
     self.parent = parent
     self.index = index
     self.name = parent.name + "." + name

   def read(self, exp_time):
     if not self.parent.acquisition_event.is_set():
       self.parent.acquisition_event.wait()
     else:
       self.parent.read(exp_time)
     return self.parent.last_acq[self.index]

class tango_bpm(object):
   def __init__(self, name, config):
       tango_uri = config.attrib["uri"]

       self.__control = PyTango.gevent.DeviceProxy(tango_uri)
       self.__acquisition_event = gevent.event.Event()
       self.__acquisition_event.set()
       self.__last_acq = None
      
   @property
   def x(self):
     return Counter(self, "x", 2)

   @property
   def y(self):
     return Counter(self, "y", 3)

   @property
   def intensity(self):
     return Counter(self, "intensity", 1)

   @property
   def acquisition_event(self):
     return self.__acquisition_event

   @property
   def last_acq(self):
     return self.__last_acq

   def read(self, exp_time):
     try:
       self.__acquisition_event.clear()
       self.__control.ExposureTime = exp_time
       self.__last_acq = self.__control.GetPosition()
     finally:
       self.__acquisition_event.set()

   def is_acquiring(self):
     return str(self.__control.State()) == 'MOVING'

   def live(self):
     return self.__control.Live()

   def stop(self):
     return self.__control.Stop()      

   def set_in(self):
     return self.__control.In()

   def set_out(self):
     return self.__control.Out()

   def is_in(self):
     return self.__control.YagStatus == "in"

   def foil_in(self):
     return self.__control.FoilIn()

   def foil_out(self):
     return self.__control.FoilOut()

   def is_foil_in(self):
     return self.__control.FoilStatus == "in"

   def led_on(self):
     return self.__control.LedOn()

   def led_off(self):
     return self.__control.LedOff()

   def is_led_on(self):
     return self.__control.LedStatus > 0
   
