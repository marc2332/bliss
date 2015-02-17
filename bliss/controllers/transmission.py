from bliss.common.task_utils import *
from bliss.common import wrapper
import inspect
from PyTransmission import matt_control
import types

class transmission:
   def __init__(self, name, config):
      wago_ip = config["controller_ip"]
      nb_filter = config["nb_filter"]
      try:
         #fixed energy
         energy = config["energy"]
      except:
         #tunable energy
         energy = 0
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

      self.__control = matt_control.MattControl(wago_ip, nb_filter, energy, att_type, wago_alternate, stat_m, ctrl_m,datafile)

      self.__control.connect()
      wrapper.wrap_methods(self.__control, self)
