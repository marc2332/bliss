from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import READY, MOVING, OFF
from bliss.controllers.motor import add_axis_method

from PyTango.gevent import DeviceProxy
from PyTango.gevent import AttributeProxy

from PyTango import DevState

import time

"""
undulator.py : a undulator controller for bliss.
Cyril Guilloud - ESRF ISDD SOFTGROUP BLISS - Feb. 2015
"""

"""
config :
 'velocity' in unit/s
 'acceleration' in unit/s^2
 'steps_per_unit' in unit^-1  (default 1)
 'backlash' in unit
"""

config_xml = '''
<config>
  <controller class="undulator">
  <ds_name value="//orion:10000/ID/ID/30" />
    <axis name="ppu35c" class="UndulatorAxis">
      <attribute_position value="PPU35C_GAP_Position" />
      <attribute_velocity value="PPU35C_GAP_Velocity" />
      <attribute_acceleration value="PPU35C_GAP_Acceleration" />
      <attribute_FirstVelocity value="PPU35C_GAP_FirstVelocity" />

      <velocity value="5" />
      <acceleration value="100" />
      <steps_per_unit value="1" />
      <backlash value="2" />
    </axis>
  </controller>
</config>
'''


class Undulator(Controller):
    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        try:
            self.ds_name = self.config.get("ds_name")
        except:
            elog.debug("no 'ds_name' defined in config for %s" % name)

    """
    Controller initialization actions.
    """
    def initialize(self):
        # Get a proxy on Insertion Device device server of the beamline.
        self.device = DeviceProxy(self.ds_name)

    """
    Axes initialization actions.
    """
    def initialize_axis(self, axis):
        self.attr_pos_name = self.ds_name + "/" self.config.get("attribute_position")
        self.attr_vel_name = self.ds_name + "/" self.config.get("attribute_velocity")
        self.attr_acc_name = self.ds_name + "/" self.config.get("attribute_acceleration")

        self.attr_position = AttributeProxy(self.attr_pos_name)
        self.attr_velocity = AttributeProxy(self.attr_vel_name)
        self.attr_acceleration = AttributeProxy(self.attr_acc_name)

    """
    Actions to perform at controller closing.
    """
    def finalize(self):
        pass

    def start_one(self, motion, t0=None):
        self.attr_position = float(motion.target_pos / motion.axis.steps_per_unit)

    def read_position(self, axis, measured=False):
        """
        Returns the position (measured or desired) taken from controller
        in controller unit (steps).
        """
        return self.attr_position

    """
    VELOCITY
    """
    def read_velocity(self, axis):
        """
        Returns the current velocity taken from controller
        in motor units.
        """
        return self.attr_velocity

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units
        """
        print "set_velocity to ", new_velocity
        # self.attr_velocity = new_velocity

    """
    ACCELERATION
    """
    def read_acceleration(self, axis):
        return self.attr_acceleration

    def set_acceleration(self, axis, new_acceleration):
        print "Set acceleration to ", new_acceleration
        # self.attr_acceleration = new_acceleration


    """
    STATE
    """
    def state(self, axis):
        _state = self.device.state()

        if _state == DevState.ON:
            return READY
        elif _state == DevState.MOVING:
            return MOVING
        else:
            return READY

    """
    Must send a command to the controller to abort the motion of given axis.
    """
    def stop(self, axis):
        self.device.abort()

    def stop_all(self, *motion_list):
        self.device.abort()


    def get_info(self, axis):

        info_str = ""
        info_str = "DEVICE SERVER : %s \n" % self.ds_name
        info_str += self.ds.state() +"\n"
        info_str += "status=\"%s\"\n" % str(self.ds.status()).strip()
        info_str += "state=%s\n" % self.ds.state()
        info_str += "mode=%s\n" % str(self.ds.mode)
        info_str += ("undu states= %s" % " ".join(map(str, self.ds.UndulatorStates)))

        return info_str

