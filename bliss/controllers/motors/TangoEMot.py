from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING

from PyTango.gevent import DeviceProxy
from PyTango import DevState

import traceback

"""
Bliss controller tango bliss motor
TangoEMot
Cyril Guilloud ESRF BLISS November 2014

This can be used to interface a motor instanciated on a remote
computer.
"""

class TangoEMot(Controller):

    def __init__(self, name, config, axes):
        Controller.__init__(self, name, config, axes)

        # Gets DS name from xml config.
        self.ds_name = self.config.get("ds_name")

        # tests if DS is responding.


    def initialize(self):
        pass

    def finalize(self):
        pass

    def initialize_axis(self, axis):
        self.axis_proxy = DeviceProxy(self.ds_name)

        axis.config.config_dict.update( { "steps_per_unit": {"value": self.axis_proxy.steps_per_unit } } )
        axis.config.config_dict.update( { "acceleration": {"value": self.axis_proxy.ReadConfig("acceleration") } })
        axis.config.config_dict.update( { "velocity": {"value": self.axis_proxy.ReadConfig("velocity") } })

    def read_position(self, axis, measured=False):
        """
        Returns the position (measured or desired) taken from controller
        in *controller unit* (steps for example).
        """
        if measured:
            return self.axis_proxy.position * axis.steps_per_unit
        else:
            return self.axis_proxy.Measured_Position * axis.steps_per_unit

    def read_velocity(self, axis):
        _vel = self.axis_proxy.velocity * abs(axis.steps_per_unit)
        return _vel

    def set_velocity(self, axis, new_velocity):
        self.axis_proxy.velocity = new_velocity / abs(axis.steps_per_unit)

    def read_acctime(self, axis):
        return self.axis_proxy.acctime

    def set_acctime(self, axis, new_acc_time):
        self.axis_proxy.acctime = new_acc_time

    def read_acceleration(self, axis):
        return self.axis_proxy.acceleration * abs(axis.steps_per_unit)

    def set_acceleration(self, axis, new_acceleration):
        self.axis_proxy.acceleration = new_acceleration / abs(axis.steps_per_unit)

    def state(self, axis):
        _state = self.axis_proxy.state()
        if _state == DevState.ON:
            return READY
        elif _state == DevState.MOVING:
            return MOVING
        else:
            return READY

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        self.axis_proxy.position = float(motion.target_pos / motion.axis.steps_per_unit)

    def stop(self, axis):
        self.axis_proxy.Abort()

    def home_search(self, axis):
        self.axis_proxy.GoHome()

    def home_state(self, axis):
        return self.state(axis)

