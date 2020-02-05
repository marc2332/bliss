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
    controller:
      plugin: emotion         # (2)
      class: Speedgoat        # (3)
      speedgoat: goat1        # (4)
      axes:
      - name: piezo1          # (5)
        model: piezoMotor     # (6)
        velocity: 100         # (7)
        acceleration: 400     # (8)
        unit: nm              # (9)

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
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

    def initialize(self):
        redirect_goat = self.config.get("speedgoat")
        self.speedgoat = get_config().get(redirect_goat)
        self.sg_controller = self.speedgoat.motors_controller

    def initialize_axis(self, axis):
        if axis.name not in self.sg_controller.available_motors:
            raise (RuntimeError('Speedgoat: Axis "%s" does not exist' % axis.name))

        (sgLowLimit, sgHighLimit) = self.sg_controller.available_motors[
            axis.name
        ].limits()
        # axis.limits(LowLimit=sgLowLimit, HighLimit=sgHighLimit)

    def read_position(self, axis):
        return self.sg_controller.available_motors[axis.name].position / 1000.0

    def read_velocity(self, axis):
        return self.sg_controller.available_motors[axis.name].velocity / 1000.0

    def set_velocity(self, axis, velocity):
        self.sg_controller.available_motors[axis.name].velocity = velocity * 1000.0

    def read_acceleration(self, axis):
        acc_time = self.sg_controller.available_motors[axis.name].acc_time
        velocity = self.read_velocity(axis)
        return velocity / acc_time

    def set_acceleration(self, axis, acceleration):
        accel_time = self.read_velocity(axis) / float(acceleration)
        self.sg_controller.available_motors[axis.name].acc_time = accel_time

    def state(self, axis):
        if not self.speedgoat.is_app_running:
            return AxisState("OFF")
        if self.sg_controller.available_motors[axis.name].is_moving:
            return AxisState("MOVING")
        return AxisState("READY")

    def prepare_move(self, motion):
        self.sg_controller.available_motors[axis.name].prepare_move()
        self.sg_controller.available_motors[axis.name].set_point = motion.target_pos

    def start_one(self, motion):
        self.sg_controller.available_motors[motion.axis.name].start_move()

    def start_all(self, *motions):
        for m in motions:
            self.start_one(m)

    def stop_one(self, axis):
        self.sg_controller.available_motors[motion.axis.name].stop_move()

    def stop_all(self, *motions):
        for m in motions:
            self.stop_one(m)
