"""
Bliss generic library
"""
from bliss.controllers.motor import Controller
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING, UNKNOWN
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
import pdb


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
    self.libdevice = icepap.lib.System(self.host, "verb=%d"%self.libdebug)

    # Create an IcePAP lib object as default group
    self.libgroup  = icepap.lib.Group("default")


  def finalize(self):
    """Controller no more needed"""	  
    #import pdb;pdb.set_trace()
    # Remove any group in the IcePAP lib
    try:
      self.libgroup.delete()
    except:
      pass

    # Close IcePAP lib socket/threads
    self.libdevice.close()


  def initialize_axis(self, axis):
    """Axis initialization"""

    # Get axis config from bliss config
    axis.address  = axis.config.get("address", int)

    # Create an IcePAP lib axis object
    device        = self.libdevice
    address       = axis.address
    name          = axis.name
    axis.libaxis  = icepap.lib.Axis(device, address, name)

    # Add the axis to the default IcePAP lib group 
    self.libgroup.add_axis(axis.libaxis)

    # Initialiaze hardware
    self.libgroup.set_power(icepap.lib.ON, axis.libaxis)

    # Add new axis oject methods
    add_axis_method(axis, self.get_identifier)




  def position(self, axis, new_position=None, measured=False):
    """Returns axis position in motor units"""

    # Optionnal new position to set
    if new_position is not None:
      l = icepap.lib.PosList()
      l[axis.libaxis] = new_position
      self.libgroup.pos(l)

    # Always return the current position
    pos_stps = self.libgroup.pos(axis.libaxis)

    return pos_stps


  def velocity(self, axis, new_velocity=None):
    """Returns axis current velocity in user units per seconds"""


    # Optionnal new velocity to set
    if new_velocity is not None:
      l = icepap.lib.VelList()
      l[axis.libaxis] = new_velocity
      self.libgroup.velocity(l)

    # Always return the current velocity
    return self.libgroup.velocity(axis.libaxis)


  def acctime(self, axis, new_acctime=None):
    """Returns axis current acceleratin time in seconds"""

    # Optionnal new acceleration time to set
    if new_acctime is not None:
      l = icepap.lib.AcctimeList()
      l[axis.libaxis] = new_acctime
      self.libgroup.acctime(l)

    # Always return the current velocity
    return self.libgroup.acctime(axis.libaxis)



  def state(self, axis):
    """Returns the current axis state"""

    # The axis can only be accessed through a group in IcePAP lib
    # Use the default group
    status = self.libgroup.status(axis.libaxis)

    # Convert status formats
    if(icepap.lib.status_ismoving(status)):
      return MOVING
    if(icepap.lib.status_isready(status)):
      return READY

    # Abnormal end
    return UNKNOWN


  def prepare_move(self, motion):
    """Called once before an axis motion, positions in motor units"""
    pass

  def start_one(self, motion):
    """Launch an axis moition, returns immediately, positions in motor units"""
    target_positions = icepap.lib.PosList()
    target_positions[motion.axis.libaxis] = motion.target_pos
    self.libgroup.move(target_positions)


  def stop(self, axis):
    """Stops smoothly an axis motion"""
    self.libgroup.stop(axis.libaxis)


  def abort(self, axis):
    """Stops as fast as possible an axis motion, emergency stop"""


  def _set_lib_verbose(self, val): 
    """Change IcePAP library verbose level"""
    self.libdevice.set_verbose(val)


  def get_identifier(self, axis):
    """Returns the unique string identifier of the specified axis"""
    return self.libgroup.command("?ID", axis.libaxis)

