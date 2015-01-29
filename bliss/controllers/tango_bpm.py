from bliss.common.task_utils import cleanup, error_cleanup, task
import time
import gevent
import PyTango.gevent


class BpmCounter:
   def __init__(self, parent, name, index=None):
     self.parent = parent
     self.index = index
     self._name = name
     self.name = parent.name + "." + name

   def read(self, exp_time=None):
     if self.index is None:
       return getattr(self.parent, self._name)()
     else:
       if not self.parent.acquisition_event.is_set():
         self.parent.acquisition_event.wait()
         data = self.parent.last_acq
       else:
         data = self.parent.read(exp_time)
       return data[self.index]


class tango_bpm(object):
   def __init__(self, name, config):
       self.name = name

       tango_uri = config.get("uri")

       self.__control = PyTango.gevent.DeviceProxy(tango_uri)
       self.__acquisition_event = gevent.event.Event()
       self.__acquisition_event.set()
       self.__last_acq = None
      
   @property
   def x(self):
     return BpmCounter(self, "x", 2)

   @property
   def y(self):
     return BpmCounter(self, "y", 3)

   @property
   def intensity(self):
     return BpmCounter(self, "intensity", 1)

   @property
   def diode_current(self):
     return BpmCounter(self, "_read_diode_current")

   @property
   def acquisition_event(self):
     return self.__acquisition_event

   @property
   def last_acq(self):
     return self.__last_acq

   def read(self, exp_time=None):
     try:
       self.__acquisition_event.clear()
       if exp_time is not None:
           self.__control.ExposureTime = exp_time
       self.__last_acq = self.__control.GetPosition()
       return self.__last_acq[:]
     finally:
       self.__acquisition_event.set()

   def _read_diode_current(self):
     return self.__control.DiodeCurrent

   def set_diode_range(self, range):
     self.__control.DiodeRange = range

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
   
