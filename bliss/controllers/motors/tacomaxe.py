# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import os
from Taco import TacoDevice
import time

from bliss.controllers.motor import Controller
from bliss.common import log
from bliss.common.axis import AxisState

from bliss.common.utils import object_method

"""
TacoMaxe: TacoDevice controller library
"""

"""
Global resources
"""
# status 45:ALARM is not handled by bliss
maxe_states = {2: "READY", 23: "FAULT", 9: "MOVING"}


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

    def __init__(self, *args, **kwargs):
        """Contructor"""
        Controller.__init__(self, *args, **kwargs)

    def initialize(self):
        """Controller initialization"""
        tacomaxe_info("initialize() called")

        # Get controller from bliss config
        self.taconame = self.config.get("tacodevice")
        log.info("my taconame is %r" % self.taconame)
        self.device = TacoDevice(self.taconame)

    def initialize_axis(self, axis):
        """Axis initialization"""
        tacomaxe_info('initialize_axis() called for axis "%s"' % axis.name)

        # Get axis config from bliss config
        axis.channel = axis.config.get("channel", int)

    def finalize(self):
        """ Actions to perform at controller closing """
        tacomaxe_info("finalize() called")
        pass

    def set_on(self, axis):
        """Switch power on"""
        tacomaxe_info('Power on called for axis "%s"' % axis.name)
        self.device.DevEnablePower(axis.channel)

    def set_off(self, axis):
        """Switch power off"""
        tacomaxe_info('Power off called for axis "%s"' % axis.name)
        self.device.DevDisablePower(axis.channel)

    def read_position(self, axis, measured=False):
        """Returns real axis position -- in motorunit (steps) --"""
        tacomaxe_info('position() called for axis "%s"' % axis.name)
        ctrl_pos = self.device.DevReadPosition(axis.channel)
        return ctrl_pos

    def set_position(self, axis, new_pos):
        """Sets the axis position 
	   Returns the position -- in motorunit (steps) --
	"""
        tacomaxe_info('set_position(%f) called for axis "%s"' % (new_pos, axis.name))
        self.device.DevLoadPosition(axis.channel, new_pos)
        return self.read_position(axis)

    def read_velocity(self, axis):
        """Returns axis current velocity -- in motorunits/sec --"""
        tacomaxe_info('read_velocity called for axis "%s"' % (axis.name))
        steps_vel = self.device.DevReadVelocity(axis.channel)
        return steps_vel

    def set_velocity(self, axis, new_velocity):
        """Set axis velocity  -- in motorunits/sec -- """
        s = "%f" % new_velocity
        tacomaxe_info('set_velocity(%s) called for axis "%s"' % (s, axis.name))
        self.device.DevSetVelocity(axis.channel, new_velocity)
        # Always return the current velocity
        return self.read_velocity(axis)

    def set_firstvelocity(self, axis, fsr):
        """Sets the firststeprate (velocity at start) in motorunits/sec """
        tacomaxe_info('set_firstvelocity(%f) called for axis "%s"' % (fsr, axis.name))
        self.device.DevSetFirstStepRate(axis.channel, fsr)

    def read_firstvelocity(self, axis):
        """Returns axis current firstvelocity -- in motorunits/sec --"""
        tacomaxe_info('read_firstvelocity called for axis "%s"' % (axis.name))
        steps_vel = self.device.DevReadFStepRate(axis.channel)
        print steps_vel
        return steps_vel

    def read_acceleration(self, axis):
        """Returns axis current acceleration in motorunits/sec2"""
        tacomaxe_info('read_acceleration called for axis "%s"' % (axis.name))
        accel = self.device.DevReadAcceleration(axis.channel)

        return accel

    def set_acceleration(self, axis, new_acc):
        """Set axis acceleration given in motorunits/sec2"""
        s = "%f" % new_acc
        tacomaxe_info('set_acceleration(%s) called for axis "%s"' % (s, axis.name))
        self.device.DevSetAcceleration(axis.channel, new_acc)
        return self.read_acceleration(axis)

    def state(self, axis):
        """Returns the current axis (motor) state"""
        tacomaxe_info('state() called for axis "%s"' % axis.name)
        status = self.device.DevReadState(axis.channel)
        status_motor = AxisState(maxe_states[status[0]])
        tacomaxe_debug('status motor = "%s"' % status_motor)
        statuslim = self.device.DevReadSwitches(axis.channel)
        """ It is NEGATLIMIT - POSITLIMIT - NEGPOSLIMIT - LIMITSOFF """
        tacomaxe_debug('status limit = "%x"' % statuslim)
        if statuslim == "NEGATLIMIT":
            status_limit = "LIMNEG"
        elif statuslim == "POSITLIMIT":
            status_limit = "LIMPOS"
        elif statuslim == "NEGPOSLIMIT":
            """ only one limit for bliss """
            status_limit = "NEGATLIMIT"
        else:
            status_limit = "NONE"
        """ HOME not managed """
        tacomaxe_debug('status limit = "%s"' % status_limit)
        """ returns a global view ..."""
        if status_limit != "NONE":
            return status_limit
        else:
            return status_motor

    def home_search(self, axis, switch):
        """Launch a homing sequence"""
        tacomaxe_info('home_search() called for axis "%s"' % axis.name)
        self.device.DevMoveReference(axis.channel, switch)

    def home_state(self, axis):
        """Returns the current axis state while homing"""
        tacomaxe_info('home_state() called for axis "%s"' % axis.name)
        return self.state(axis)

    def limit_search(self, axis, limit):
        """
        Launch a limitswitch search sequence
        the sign of the argin gives the search direction
        """
        tacomaxe_info('limit_search() called for axis "%s"' % axis.name)
        self.device.DevSetContinuous(axis.channel, limit)

    def prepare_move(self, motion):
        """
        Called once before a single axis motion,
        positions in motor units
        """
        tacomaxe_info(
            "prepare_move() called for axis %r: moving to %f (controller unit)"
            % (motion.axis.name, motion.target_pos)
        )
        pass

    def start_one(self, motion):
        """
        Called on a single axis motion,
        returns immediately,
        positions in motor units
        """
        tacomaxe_info(
            "start_one() called for axis %r: moving to %f (controller unit)"
            % (motion.axis.name, motion.target_pos)
        )
        self.device.DevMoveAbsolute(motion.axis.channel, motion.target_pos)

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
        self.device.DevAbortCommand(axis.channel)

    def stop_all(self, *motion_list):
        """Stops all the moving axis given"""
        for motion in motion_list:
            self.stop(motion.axis)

    @object_method(types_info=("None", "float"))
    def custom_read_firststeprate(self, axis):
        """Returns axis current firstvelocity -- in motorunits/sec --"""
        tacomaxe_info('custom_read_firststeprate() called for axis "%s"' % axis.name)
        fsteps_vel = self.device.DevReadFStepRate(axis.channel)
        print fsteps_vel
        return fsteps_vel

    @object_method(types_info=("float", "None"))
    def custom_set_firststeprate(self, axis, fsr):
        """Sets axis current firstvelocity -- in motorunits/sec --"""
        tacomaxe_info(
            'custom_set_firststeprate(%f) called for axis "%s"' % (fsr, axis.name)
        )
        self.device.DevSetFirstStepRate(axis.channel, fsr)
        return self.device.DevReadFStepRate(axis.channel)
