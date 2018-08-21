# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Spec motor controller
"""
import math
import gevent
from bliss.common.utils import object_method
from bliss.comm.spec.error import SpecClientTimeoutError
from bliss.comm.spec.connection import SpecConnection
from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState, NoSettingsAxis


class Spec(Controller):
    def __init__(self, name, config, axes, *args, **kwargs):
        new_axes = []
        for axis_cfg in map(list, axes):
            # change class name for axes created by this controller
            # to NoSettingsAxis: no settings will be stored in redis,
            # thus forcing to ask spec every time (no cache)
            axis_cfg[1] = NoSettingsAxis
            # make sure steps per unit is 1, to avoid conversions
            # between spec units and Bliss units
            assert axis_cfg[2].get("steps_per_unit", int) == 1
            new_axes.append(axis_cfg)

        Controller.__init__(self, name, config, new_axes, *args, **kwargs)

    def initialize(self):
        self.connection = SpecConnection(self.config.get("spec"))

    def initialize_axis(self, axis):
        axis.mnemonic = axis.config.get("mnemonic")

    def _read_channel(self, motor_mnemonic, channel_name):
        with gevent.Timeout(3, SpecClientTimeoutError):
            channel = self.connection.getChannel(
                "motor/%s/%s" % (motor_mnemonic, channel_name)
            )
            return channel.read(timeout=1, force_read=True)

    def read_position(self, axis):
        return self._read_channel(axis.mnemonic, "position")

    def read_velocity(self, axis):
        step_size = math.fabs(self._read_channel(axis.mnemonic, "step_size"))
        return self._read_channel(axis.mnemonic, "slew_rate") / float(step_size)

    def set_velocity(self, axis, new_velocity):
        step_size = math.fabs(self._read_channel(axis.mnemonic, "step_size"))
        channel = self.connection.getChannel("motor/%s/slew_rate" % axis.mnemonic)
        channel.write(int(new_velocity * step_size), wait=True)
        gevent.sleep(0.1)

    def read_acceleration(self, axis):
        acctime = self._read_channel(axis.mnemonic, "acceleration") / 1000.
        return self.read_velocity(axis) / float(acctime)

    def set_acceleration(self, axis, new_acc):
        acctime = 1000. * self.read_velocity(axis) / float(new_acc)
        channel = self.connection.getChannel("motor/%s/acceleration" % axis.mnemonic)
        channel.write(int(acctime), wait=True)
        gevent.sleep(0.1)

    def state(self, axis):
        move_done = self._read_channel(axis.mnemonic, "move_done")
        if move_done == 0:
            # are we on limit ?
            ll = self._read_channel(axis.mnemonic, "low_lim_hit")
            if ll:
                return AxisState("READY", "LIMNEG")
            hl = self._read_channel(axis.mnemonic, "high_lim_hit")
            if hl:
                return AxisState("READY", "LIMPOS")
            return AxisState("READY")
        return AxisState("MOVING")

    def start_one(self, motion):
        c = self.connection.getChannel("motor/%s/start_one" % motion.axis.mnemonic)
        c.write(motion.target_pos, wait=True)
        # move_done passes to 1, but not immediately;
        # and not always! (for example if a pseudo motor is moved instead
        # of a macro motor or a real motor)
        # in this case, the timeout will exit -- no error is displayed
        acctime = self._read_channel(motion.axis.mnemonic, "acceleration") / 1000.
        with gevent.Timeout(1, False):
            while self._read_channel(motion.axis.mnemonic, "move_done") == 0:
                gevent.sleep(acctime)

    def stop(self, axis):
        self.connection.send_msg_abort(wait=True)

    @object_method(types_info=("str", "str"))
    def get_parameter(self, axis, param):
        return str(self._read_channel(axis.mnemonic, param))

    @object_method(types_info=("str", "str"))
    def set_parameter(self, axis, param, value):
        c = self.connection.getChannel("motor/%s/%s" % (axis.mnemonic, param))
        c.write(value)
