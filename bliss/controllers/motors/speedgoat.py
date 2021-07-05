# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Speedgoat motor controller

YAML_ configuration example:

.. code-block:: yaml

    # speedgoat definition (maybe in another file):
    simulink:
      plugin: bliss     # (1)
      module: simulink
      class: Speedgoat
      name: goat1
      url: pcmel1

    # Speedgoat motor controller:
    plugin: emotion
    package: bliss.controllers.motors.speedgoat
    class: SpeedgoatMotor
    speedgoat: $goat1
    axes:
      - name: fjpur
        velocity: 1.0
        acceleration: 10
        steps_per_unit: 1000
        unit: um

#. simulink YAML_ definition (see: :mod:`bliss.controllers.simulink`)
#. emotion plugin (inherited)
#. emotion class (mandatory = 'Speedgoat')
#. reference to the speedgoat object name (mandatory)
#. axis name (mandatory)
#. name of the speedgoat axis in the simulink model (mandatory)
#. axis velocity (mandatory)
#. axis acceleration (mandatory)
#. axis units (optional)

"""

from bliss.common.axis import AxisState
from bliss.config.static import get_config
from bliss.controllers.motor import Controller
from bliss.common.utils import object_attribute_get


class SpeedgoatMotor(Controller):
    def _load_config(self):
        super()._load_config()
        self.speedgoat = self.config.get("speedgoat")
        self._axis_init_done = {}

    def initialize(self):
        self.sg_controller = self.speedgoat.motors_controller

    def initialize_axis(self, axis):
        if axis.name not in self.sg_controller.available_motors:
            raise (RuntimeError('Speedgoat: Axis "%s" does not exist' % axis.name))

        if (
            axis.name not in self._axis_init_done.keys()
            or self._axis_init_done[axis.name] == False
        ):
            self._axis_init_done[axis.name] = True
            try:
                (sgLowLimit, sgHighLimit) = self.sg_controller.available_motors[
                    axis.name
                ].limits()
                axis.low_limit = sgLowLimit / axis.steps_per_unit
                axis.high_limit = sgHighLimit / axis.steps_per_unit
            except:
                self._axis_init_done[axis.name] = False

    def read_position(self, axis):
        position = self.sg_controller.available_motors[axis.name].position
        return position

    def read_velocity(self, axis):
        velocity = self.sg_controller.available_motors[axis.name].velocity
        return velocity

    def set_velocity(self, axis, velocity):
        self.sg_controller.available_motors[axis.name].velocity = int(velocity)

    def read_acceleration(self, axis):
        acc_time = self.sg_controller.available_motors[axis.name].acc_time
        velocity = self.read_velocity(axis)
        return velocity / acc_time

    def set_acceleration(self, axis, acceleration):
        accel_time = self.read_velocity(axis) / acceleration
        self.sg_controller.available_motors[axis.name].acc_time = accel_time

    def state(self, axis):
        if not self.speedgoat.is_app_running:
            return AxisState("OFF")
        state = self.sg_controller.available_motors[axis.name].is_moving
        if state == 1:
            return AxisState("MOVING")
        return AxisState("READY")

    def prepare_move(self, motion):
        self.sg_controller.available_motors[motion.axis.name].prepare_move()
        self.sg_controller.available_motors[
            motion.axis.name
        ].set_point = motion.target_pos

    def start_one(self, motion):
        self.sg_controller.available_motors[motion.axis.name].start_move()

    def start_all(self, *motions):
        for m in motions:
            self.start_one(m)

    def stop_one(self, axis):
        self.sg_controller.available_motors[axis.name].stop()

    def stop_all(self, *motions):
        for m in motions:
            self.stop_one(m.axis)
