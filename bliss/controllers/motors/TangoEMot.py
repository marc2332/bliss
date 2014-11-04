from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import READY, MOVING

from PyTango.gevent import DeviceProxy
from PyTango import DevState

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

    def read_position(self, axis, measured=False):
        """
        Returns position's setpoint or measured position.
        """
        if measured:
            return self.axis_proxy.position
        else:
            return self.axis_proxy.Measured_Position

    def read_velocity(self, axis):
        return self.axis_proxy.velocity

    def set_velocity(self, axis, new_velocity):
        self.axis_proxy.velocity = new_velocity
        return new_velocity

    def read_acctime(self, axis):
        return self.axis_proxy.acctime

    def set_acctime(self, axis, new_acc_time):
        self.axis_proxy.acctime = new_acc_time
        return new_acc_time

    def read_acceleration(self, axis):
        return self.axis_proxy.acceleration

    def set_acceleration(self, axis, new_acceleration):
        self.axis_proxy.acceleration = new_acceleration
        return new_acceleration

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
        self.axis_proxy.position = motion.target_pos

    def stop(self, axis):
        self.axis_proxy.Abort()

    def home_search(self, axis):
        self.axis_proxy.GoHome()

    def home_state(self, axis):
        return READY
