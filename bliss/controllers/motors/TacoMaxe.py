import sys
import os
import Taco.TacoDevice as MyTacoDevice
import time

"""
TacoMaxe: TacoDevice controller library
"""
from bliss.controllers.motor import Controller; from bliss.common import log
from bliss.controllers.motor import add_axis_method
from bliss.common.axis import AxisState

"""
Global resources
"""
#status 45:ALARM is not handled by bliss
maxe_states = {2:"READY", 23:"FAULT", 9:"MOVING"}


def tacomaxe_info(msg):
    """Logging method"""
    log.info("[TacoMaxe]" + msg)

def tacomaxe_err(msg):
    """Logging method"""
    log.error("[TacoMaxe]" + msg)

def tacomaxe_debug(msg):
    """Logging method"""
    log.debug("[TacoMaxe]" + msg)

class TacoMaxe(Controller):

    """Implement the bridge to a MAXE like taco controller :
	- MaxeVpapds linux server to VPAP controller
	- Maxe OS9 server to VPAP controller
	- A3200 server to Aerotech controller
	- Dsc2p server to ETEL Dsc2p controller 
    """

    def __init__(self, name, config, axes, encoders):
        """Contructor"""
        Controller.__init__(self, name, config, axes, encoders)

 
    def initialize(self):
        """Controller initialization"""
        tacomaxe_info("initialize() called")

        # Get controller from bliss config
        self.taconame = self.config.get("tacodevice")
        log.info("my taconame is %r"%self.taconame)
	self.device = MyTacoDevice.TacoDevice(self.taconame)


    def initialize_axis(self, axis):
        """Axis initialization"""
        tacomaxe_info("initialize_axis() called for axis \"%s\"" % axis.name)

        # Get axis config from bliss config
        axis.channel = axis.config.get("channel", int)
        axis.myvelocity = axis.config.get("velocity", int)
        axis.mybacklash = axis.config.get("backlash", int)
        axis.myacceleration = axis.config.get("acceleration", int)
        axis.steps_per_u = axis.config.get("steps_per_unit", int)

	add_axis_method(axis, self.custom_read_firststeprate,types_info=("None","float"))
	add_axis_method(axis, self.custom_set_firststeprate,types_info=("float","None"))

    def finalize(self):
    	""" Actions to perform at controller closing """
        tacomaxe_info("finalize() called")
	pass

    def read_position(self, axis, measured=False):
        """Returns real axis position -- in motorunit (steps) --"""
        tacomaxe_info("position() called for axis \"%s\"" % axis.name)
	ctrl_pos = self.device.DevReadPosition(axis.channel)
        return ctrl_pos

    def set_position(self, axis, new_pos):
	"""Sets the axis position 
	   Returns the position -- in motorunit (steps) --
	"""
	self.device.DevLoadPosition(axis.channel,new_pos)
        return self.read_position(axis)

    def read_velocity(self, axis):
        """Returns axis current velocity -- in motorunits/sec --"""
	tacomaxe_info("read_velocity called for axis \"%s\"" %
                      (axis.name))
	steps_vel = self.device.DevReadVelocity(axis.channel)
        return steps_vel

    def set_velocity(self, axis, new_velocity):
        """Set axis velocity  -- in motorunits/sec -- """
        s = "%f" % new_velocity
        tacomaxe_info("set_velocity(%s) called for axis \"%s\"" %
                      (s, axis.name))
        axis.myvelocity = new_velocity
 	self.device.DevSetVelocity(axis.channel, new_velocity)
        # Always return the current velocity
        return self.read_velocity(axis)

    def set_firstvelocity(self, axis, fsr):
	"""Sets the firststeprate (velocity at start) in motorunits/sec """
	self.device.DevSetFirstStepRate(axis.channel,fsr)

    def read_firstvelocity(self,axis):
        """Returns axis current firstvelocity -- in motorunits/sec --"""
        tacomaxe_info("read_firstvelocity called for axis \"%s\"" %
                      (axis.name))
	steps_vel = self.device.DevReadFirstStepRate(axis.channel)
        print steps_vel
        return steps_vel

    def read_acceleration(self, axis):
        """Returns axis current acceleration in motorunits/sec2"""
        tacomaxe_info("read_acceleration called for axis \"%s\"" %
                      (axis.name))
        accel  = self.device.DevReadAcceleration(axis.channel)
        return accel

    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in motorunits/sec2"""
        s = "%f" % new_acc
        tacomaxe_info("set_acceleration(%s) called for axis \"%s\"" %
                      (s, axis.name))
        self.device.DevSetAcceleration(axis.channel, new_acc)
        return self.read_acceleration(axis)

    def state(self, axis):
        """Returns the current axis (motor) state"""
        tacomaxe_info("state() called for axis \"%s\"" % axis.name)

        status = self.device.DevReadState(axis.channel)
	return AxisState(maxe_states[status[0]])

    def prepare_move(self, motion):
        """
        Called once before a single axis motion,
        positions in motor units
        """
        tacomaxe_info("prepare_move() called for axis %r: moving to %f (controller unit)" %
                      (motion.axis.name,motion.target_pos))
        pass

    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        tacomaxe_info("start_one() called for axis %r: moving to %f (controller unit)" %
                      (motion.axis.name,motion.target_pos))
        self.device.DevMoveAbsolute(motion.axis.channel,motion.target_pos)

    def start_all(self, *motion_list):
        """
        Called once per controller with all the axis to move
        returns immediately,
        positions in motor units
        """
        tacomaxe_info("start_all() called")
        for motion in motion_list:
            self.start_one(motion)

    def stop(self, axis):
        """Stops an axis motion"""
        tacomaxe_info("stop() called for axis \"%s\"" % axis.name)
	self.device.DevAbortCommand(axis.channel)


    def stop_all(self, *motion_list):
        """Stops all the moving axis given"""
        for motion in motion_list:
            self.stop(motion)

    def custom_read_firststeprate(self,axis):
        """Returns axis current firstvelocity -- in motorunits/sec --"""
        tacomaxe_info("custom_read_firststeprate() called for axis \"%s\"" % axis.name)
	fsteps_vel = self.device.DevReadFStepRate(axis.channel)
        print fsteps_vel
        return fsteps_vel

    def custom_set_firststeprate(self,axis,fsr):
        """Sets axis current firstvelocity -- in motorunits/sec --"""
        tacomaxe_info("custom_set_firststeprate(%f) called for axis \"%s\"" % (fsr,axis.name))
	self.device.DevSetFirstStepRate(axis.channel,fsr)
        return self.device.DevReadFStepRate(axis.channel)

