# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task_utils import cleanup, error_cleanup, task
from bliss.common.utils import add_property
from bliss.common.measurement import CounterBase, Reading
from bliss.common import Actuator
import gevent
from gevent import event
import PyTango.gevent
import numpy

class BpmCounter(CounterBase):
    def __init__(self, parent, name, index):
        CounterBase.__init__(self, parent.name+'.'+name)
        self.parent = parent
        self.index = index

    def read(self):
        data = self.parent.last_acq
        reading = Reading()
        try:
            reading.value = data[self.index]
        except TypeError:
            raise RuntimeError("No data available, hint: acquire data with `.count(acq_time)` first")
        else:
            reading.timestamp = data[0]
            return reading

    def count(self, acq_time):
        if not self.parent._acquisition_event.is_set():
            # acquisition in progress
            self.parent._acquisition_event.wait()
        else:
            self.parent.read(acq_time)
       

class tango_bpm(object):
   def __init__(self, name, config):
       self.name = name

       tango_uri = config.get("uri")
       foil_actuator_name = config.get("foil_name")

       self.__control = PyTango.gevent.DeviceProxy(tango_uri)
       self._acquisition_event = event.Event()
       self._acquisition_event.set()
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
     return BpmCounter(self, "x", 1)

   @property
   def y(self):
     return BpmCounter(self, "y", 2)

   @property
   def intensity(self):
     return BpmCounter(self, "intensity", 3)

   @property
   def fwhm_x(self):
     return BpmCounter(self, "fwhm_x", 4)
 
   @property
   def fwhm_y(self):
     return BpmCounter(self, "fwhm_y", 5)

   @property
   def last_acq(self):
     return self.__last_acq

   def read(self, acq_time=0):
     self._acquisition_event.clear()
     self.__last_acq = None
     back_to_live = False
     exp_time = self.__control.ExposureTime
     try:
       if str(self.__control.LiveState) == 'RUNNING':
         back_to_live = True
         self.stop()
       self.__control.AcquirePositions(acq_time)
       gevent.sleep(acq_time)
       while self.is_acquiring():
         gevent.sleep(exp_time)
       data = self.__control.AcquisitionSpectrum
       timestamp = data[0][0]
       self.__last_acq = numpy.mean(data, axis=1)
       self.__last_acq[0] = timestamp
       if back_to_live:
         self.live()
       return self.__last_acq
     finally:
       self._acquisition_event.set()

   def _read_diode_current(self, acq_time=None):
     meas = AverageMeasurement()
     for reading in meas(acq_time):
         reading.value = self.__control.DiodeCurrent
     return meas.average

   def set_diode_range(self, range):
     self.__control.DiodeRange = range

   def get_diode_range(self):
     return  self.__control.DiodeRange
   
   def set_exposure_time(self, exp_time):
     self.__control.ExposureTime = exp_time
  
   @property 
   def exposure_time(self):
     return self.__control.ExposureTime 

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

