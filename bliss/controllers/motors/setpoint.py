# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState

import math
import time

import gevent.event
from bliss.common import event
from bliss.common.tango import AttributeProxy, DeviceProxy

"""
setpoint.py : 'setpoint' EMotion controller is a close copy of mockup
controller to drive a tango attributes as an bliss motor. It is used
as rampe generator for hexapiezo for example.
"""

"""
<config>
  <controller class="setpoint" name="test">
    <port value="5000" />
    <target_attribute value="id16ni/HpzLoop/1/Ty" />
    <gating_ds value="id16ni/bliss_e517b/p1" />
    <axis name="sp1">
      <velocity value="1" />
      <acceleration value="1" />
      <steps_per_unit value="1" />
    </axis>
  </controller>
</config>
"""


class setpoint(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._axis_moves = {}

        self.factor = 1

        # config
        _target_attribute_name = self.config.get("target_attribute")
        _gating_ds = self.config.get("gating_ds")

        try:
            self.target_attribute = AttributeProxy(_target_attribute_name)
        except:
            self._logger.error(
                "Unable to connect to attrtribute %s " % _target_attribute_name
            )

        # External DS to use for gating.
        # ex: PI-E517 for zap of HPZ.
        if _gating_ds is not None:
            self.gating_ds = DeviceProxy(_gating_ds)
            self.external_gating = True
            self._logger.info("external gating True ; gating ds= %s " % _gating_ds)
        else:
            # No external gating by default.
            self.external_gating = False

        # _pos0 must be in controller unit.
        self._pos0 = self.target_attribute.read().value * self.factor
        self._logger.info("initial position : %g (in ctrl units)" % self._pos0)

    def move_done_event_received(self, state):
        if self.external_gating:
            if state:
                self._logger.debug("movement is finished  %f" % time.time())
                self.gating_ds.SetGate(False)
            else:
                self._logger.debug("movement is starting  %f" % time.time())
                self.gating_ds.SetGate(True)

    """
    Controller initialization actions.
    """

    def initialize(self):
        pass

    """
    Axes initialization actions.
    """

    def initialize_axis(self, axis):
        self._axis_moves[axis] = {"end_t": 0, "end_pos": self._pos0}

        # "end of move" event
        event.connect(axis, "move_done", self.move_done_event_received)

    """
    Actions to perform at controller closing.
    """

    def finalize(self):
        pass

    def start_all(self, *motion_list):
        t0 = time.time()
        for motion in motion_list:
            self.start_one(motion, t0=t0)

    def start_one(self, motion, t0=None):
        axis = motion.axis
        t0 = t0 or time.time()
        pos = self.read_position(axis)

        v = self.read_velocity(axis) * axis.steps_per_unit
        self._axis_moves[axis] = {
            "start_pos": pos,
            "delta": motion.delta,
            "end_pos": motion.target_pos,
            "end_t": t0 + math.fabs(motion.delta) / float(v),
            "t0": t0,
        }

    def read_position(self, axis):
        """
        Returns the position taken from controller
        in controller unit (steps).
        """
        # Always return position
        if self._axis_moves[axis]["end_t"]:
            # motor is moving
            t = time.time()
            v = self.read_velocity(axis) * axis.steps_per_unit
            d = math.copysign(1, self._axis_moves[axis]["delta"])
            dt = t - self._axis_moves[axis]["t0"]
            pos = self._axis_moves[axis]["start_pos"] + d * dt * v

            self.target_attribute.write(pos)

            return pos
        else:
            _end_pos = self._axis_moves[axis]["end_pos"] / axis.steps_per_unit

            self.target_attribute.write(_end_pos)
            return _end_pos

    def read_encoder(self, encoder):
        return self.target_attribute.read().value * self.factor

    def read_velocity(self, axis):
        """
        Returns the current velocity taken from controller
        in motor units.
        """
        _user_velocity = axis.settings.get("velocity")
        _mot_velocity = _user_velocity * axis.steps_per_unit
        return float(_mot_velocity)

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units
        Returns velocity in motor units.
        """
        _user_velocity = new_velocity / axis.steps_per_unit
        axis.settings.set("velocity", _user_velocity)

        return new_velocity

    def read_acceleration(self, axis):
        return 1

    def set_acceleration(self, axis, new_acc):
        pass

    """
    Always return the current acceleration time taken from controller
    in seconds.
    """

    def read_acctime(self, axis):
        return float(axis.settings.get("acctime"))

    def set_acctime(self, axis, new_acctime):
        axis.settings.set("acctime", new_acctime)
        return new_acctime

    """
    """

    def state(self, axis):
        if self._axis_moves[axis]["end_t"] > time.time():
            return AxisState("MOVING")
        else:
            self._axis_moves[axis]["end_t"] = 0
            return AxisState("READY")

    """
    Must send a command to the controller to abort the motion of given axis.
    """

    def stop(self, axis):
        self._axis_moves[axis]["end_pos"] = self.read_position(axis)
        self._axis_moves[axis]["end_t"] = 0

    def stop_all(self, *motion_list):
        for motion in motion_list:
            axis = motion.axis
            self._axis_moves[axis]["end_pos"] = self.read_position(axis)
            self._axis_moves[axis]["end_t"] = 0

    def home_search(self, axis, switch):
        self._axis_moves[axis]["end_pos"] = 0
        self._axis_moves[axis]["end_t"] = 0
        self._axis_moves[axis]["home_search_start_time"] = time.time()

    #    def home_set_hardware_position(self, axis, home_pos):
    #        raise NotImplementedError

    def home_state(self, axis):
        if (time.time() - self._axis_moves[axis]["home_search_start_time"]) > 2:
            return AxisState("READY")
        else:
            return AxisState("MOVING")
