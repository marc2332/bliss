"""
Bliss generic library
"""
from bliss.controllers.motor import Controller
from bliss.common.axis import READY, MOVING
from bliss.common.task_utils import task, error_cleanup, cleanup



"""
IcePAP specific library
"""
import icepap.lib



"""
"""
import random
import math
import time



class IcePAP(Controller):
  """Implement IcePAP stepper motor controller access"""

  def __init__(self, name, config, axes):
    """Contructor"""
    Controller.__init__(self, name, config, axes)


  def initialize(self):
    """Controller initialization"""

    # Get controller config from bliss config
    # Mandatory parameters
    self.host = self.config.get("host")

    # Optional parameters
    try:
      self.libdebug = int(self.config.get("libdebug"))
    except:
      self.libdebug = 1

    # Create an IcePAP lib object to access the MASTER
    self.libdevice = icepap.lib.Device(self.host, "verb=%d"%self.libdebug)

    # Create an IcePAP lib object as default group
    self.libgroup  = icepap.lib.Group("default")


  def finalize(self):
    """Controller no more needed"""	  
    try:
      self.libgroup.delete()
    except:
      pass


  def initialize_axis(self, axis):
    """Axis initialization"""

    # Get axis config from bliss config
    axis.address  = axis.config.get("address", int)
    axis.step_size= axis.config.get("step_size", float)

    # Create an IcePAP lib axis object
    device        = self.libdevice
    address       = axis.address
    name          = axis.name
    axis.libaxis  = icepap.lib.Axis(device, address, name)

    # Add the axis to the default IcePAP lib group 
    self.libgroup.add_axis(axis.libaxis)


  def read_position(self, axis):
    """Returns axis position in user units"""

    # The axis can only be accessed through a group in IcePAP lib
    # Use the default group
    pos_stps = self.libgroup.pos([axis.libaxis])[axis.libaxis]

    # Position unit convertion
    return pos_stps/axis.step_size


  def read_velocity(self, axis):
    """Returns axis current velocity in user units per seconds"""
    """    
    return self.axis_settings.get(axis, "velocity")
    """    

  def read_state(self, axis):
    """Returns the current axis state"""
    return READY
    """    
    if self._get_closed_loop_status():
      if self._get_on_target_status():
        return READY
      else:
        return MOVING
    else:
      raise RuntimeError("closed loop disabled")
    """    

  def prepare_move(self, axis, target_pos, delta):
    """Called once before an axis motion"""


  def start_move(self, axis, target_pos, delta):
    """Launch an axis moition, returns immediately"""
    """    
    self.sock.write("MOV 1 %g\n"%self._target_pos)
    """    

  def stop(self, axis):
    """Stops smoothly an axis motion"""
    """    
    # to check : copy of current position into target position ???
    self.sock.write("STP\n")
    """    

  def stop(self, axis):
    """Stops as fast as possible an axis motion, emergency stop"""



"""
  def _get_pos(self, measured=False):
    if measured:
      _ans = self.sock.write_readline("POS?\n")
    else:
      _ans = self.sock.write_readline("MOV?\n")

    # _ans should looks like "1=-8.45709419e+01\n"
    # "\n" removed by tcp lib.
    _pos = float(_ans[2:])

    return _pos

  def _get_identifier(self):
    return self.sock.write_readline("IDN?\n")

  def _get_closed_loop_status(self):
    _ans = self.sock.write_readline("SVO?\n")

    if _ans == "1=1":
      return True
    elif _ans == "1=0":
      return False
    else:
      return -1

  def _get_on_target_status(self):
    _ans = self.sock.write_readline("ONT?\n")

    if _ans =="":
      return True
    elif _ans =="":
      return False
    else:
      return -1

  def _get_error(self):
    _error_number = self.sock.write_readline("ERR?\n")
    _error_str = pi_gcs.get_error_str(_error_number)

    return (_error_number, _error_str)

  def _get_infos(self):
    _infos = [
      ("identifier                 ", "IDN?\n"),
      ("com level                  ", "CCL?\n"),
      ("Real Position              ", "POS?\n"),
      ("Setpoint Position          ", "MOV?\n"),
      ("Position low limit         ", "SPA? 1 0x07000000\n"),
      ("Position High limit        ", "SPA? 1 0x07000001\n"),
      ("Velocity                   ", "VEL?\n"),
      ("On target                  ", "ONT?\n"),
      ("target tolerance           ", "SPA? 1 0X07000900\n"),
      ("Sensor Offset              ", "SPA? 1 0x02000200\n"),
      ("Sensor Gain                ", "SPA? 1 0x02000300\n"),
      ("Motion status              ", "#5\n"),
      ("Closed loop status         ", "SVO?\n"),
      ("Auto Zero Calibration ?    ", "ATZ?\n"),
      ("Low  Voltage Limit         ", "SPA? 1 0x07000A00\n"),
      ("High Voltage Limit         ", "SPA? 1 0x07000A01\n")
    ]

    self.sock.flush()

    _txt = ""

    for i in _infos:
      _txt = _txt + "    %s %s\n"%(i[0],
                        self.sock.write_readline(i[1]))

    self.sock.write("TAD?\n")
    _txt = _txt + "    %s   %s \n"%("ADC value of analog input",
                                    self.sock.raw_read())

    return _txt
"""


