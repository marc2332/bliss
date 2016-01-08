from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.utils import add_property
from bliss.common.measurement import CounterBase, AverageMeasurement
from bliss.common import Actuator
import time
import gevent
import PyTango.gevent


class BpmCounter(CounterBase):
   def __init__(self, parent, name, index):
     CounterBase.__init__(self, parent.name+'.'+name)
     self.parent = parent
     self.index = index

   def read(self, exp_time=None):
     if isinstance(self.index, str):
       return getattr(self.parent, self.index)(exp_time)
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
       foil_actuator_name = config.get("foil_name")

       self.__control = PyTango.gevent.DeviceProxy(tango_uri)
       self.__acquisition_event = gevent.event.Event()
       self.__acquisition_event.set()
       self.__last_acq = None
       self.__diode_actuator = None
       self.__led_actuator = None
       self.__foil_actuator  = None

       bpm_properties = self.__control.get_property_list('*')

       if 'wago_ip' in bpm_properties:
           self.__diode_actuator = Actuator(self.__control.In, 
                                            self.__control.Out,
                                            lambda: self.__control.YagStatus == "in",
                                            lambda: self.__control.YagStatus == "out")
           self.__led_actuator  = Actuator(self.__control.LedOn,
                                           self.__control.LedOff,
                                           lambda: self.__control.LedStatus > 0)
           def diode_current(*args):
               return BpmCounter(self, "diode_current", "_read_diode_current")
           add_property(self, "diode_current", diode_current)
           def diode_actuator(*args):
               return self.__diode_actuator
           add_property(self, "diode", diode_actuator)
           def led_actuator(*args):
               return self.__led_actuator
           add_property(self, "led", led_actuator)
       if 'has_foils' in bpm_properties:
           self.__foil_actuator  = Actuator(self.__control.FoilIn,
                                            self.__control.FoilOut,
                                            lambda: self.__control.FoilStatus == "in",
                                            lambda: self.__control.FoilStatus == "out")
           def foil_actuator(*args):
               return self.__foil_actuator
           if not foil_actuator_name:
               foil_actuator_name = 'foil'
           add_property(self, foil_actuator_name, foil_actuator)

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

   def _read_diode_current(self, exp_time=None):
     meas = AverageMeasurement()
     for reading in meas(exp_time):
         reading.value = self.__control.DiodeCurrent
     return meas.average

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
     return self.__control.YagStatus == 'in'
 
   def is_out(self):
     return self.__control.YagStatus == 'out'

