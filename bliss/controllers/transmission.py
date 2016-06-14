# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.task_utils import *
from bliss.common.utils import wrap_methods
import inspect
from PyTransmission import matt_control
import types

class Energy:
   def __init__(self, energy):
      self.__energy = energy
      if isinstance(energy, float):
          self.tunable = False
      else:
          self.tunable = True
   def read(self):
      if self.tunable:
          return self.__energy.position()
      else:
          return self.__energy

class transmission:
   def __init__(self, name, config):
      wago_ip = config["controller_ip"]
      nb_filter = config["nb_filter"]
      try:
         #fixed energy
         self.energy = Energy(float(config["energy"]))
      except:
         #tunable energy: energy motor is expected
         self.energy = Energy(config["energy"])
      try:
          #attenuator type (0,1 or 2, default is 0)
          att_type = config["att_type"]
      except:
          att_type = 0
      try:
         #wago card alternation (True or False, default False)
         wago_alternate = config["wago_alternate"]
      except:
         wago_alternate = False
      try:
         #wago status module (default value "750-436")
         stat_m = config["status_module"]
      except:
         stat_m = "750-436"
      try:
         #wago control module (default value "750-530")
         ctrl_m = config["control_module"]
      except:
         ctrl_m = "750-530"
      try:
         datafile = config["datafile"]
      except:
         datafile=None

      self.__control = matt_control.MattControl(wago_ip, nb_filter, self.energy.read(), att_type, wago_alternate, stat_m, ctrl_m, datafile)

      self.__control.connect()
      wrap_methods(self.__control, self)

   def transmission_get(self):
      self.__control.set_energy(self.energy.read())
      return self.__control.transmission_get()

   def transmission_set(self, transmission):
      self.__control.set_energy(self.energy.read())
      return self.__control.transmission_set(transmission)
   
