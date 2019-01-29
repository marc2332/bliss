# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import AxisState
from bliss.common.tango import DevState, DeviceProxy, AttributeProxy

__author__ = "Cyril Guilloud - ESRF ISDD SOFTGROUP BLISS - Feb. 2015"


class ESRF_Undulator(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.axis_info = dict()

        try:
            self.ds_name = self.config.get("ds_name")
        except:
            elog.debug(
                "no 'ds_name' defined in config for %s" % self.config.get("name")
            )

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
        attr_pos_name = axis.config.get("attribute_position", str)
        attr_vel_name = axis.config.get("attribute_velocity", str)
        attr_acc_name = axis.config.get("attribute_acceleration", str)
        self.axis_info[axis] = {
            "attr_pos_name": attr_pos_name,
            "attr_vel_name": attr_vel_name,
            "attr_acc_name": attr_acc_name,
        }
        elog.debug("axis initilized--------------------------")

    """
    Actions to perform at controller closing.
    """

    def finalize(self):
        pass

    def _set_attribute(self, axis, attribute_name, value):
        self.device.write_attribute(self.axis_info[axis][attribute_name], value)

    def _get_attribute(self, axis, attribute_name):
        return self.device.read_attribute(self.axis_info[axis][attribute_name]).value

    def start_one(self, motion, t0=None):
        self._set_attribute(
            motion.axis,
            "attr_pos_name",
            float(motion.target_pos / motion.axis.steps_per_unit),
        )

    def read_position(self, axis):
        """
        Returns the position taken from controller
        in controller unit (steps).
        """
        return self._get_attribute(axis, "attr_pos_name")

    """
    VELOCITY
    """

    def read_velocity(self, axis):
        """
        Returns the current velocity taken from controller
        in motor units.
        """
        return self._get_attribute(axis, "attr_vel_name")

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units
        """
        self._set_attribute(axis, "attr_vel_name", new_velocity)

    """
    ACCELERATION
    """

    def read_acceleration(self, axis):
        return self._get_attribute(axis, "attr_acc_name")

    def set_acceleration(self, axis, new_acceleration):
        self._set_attribute(axis, "attr_acc_name", new_acceleration)

    """
    STATE
    """

    def state(self, axis):
        _state = self.device.state()

        if _state == DevState.ON:
            return AxisState("READY")
        elif _state == DevState.MOVING:
            return AxisState("MOVING")
        else:
            return AxisState("READY")

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
        info_str += self.ds.state() + "\n"
        info_str += 'status="%s"\n' % str(self.ds.status()).strip()
        info_str += "state=%s\n" % self.ds.state()
        info_str += "mode=%s\n" % str(self.ds.mode)
        info_str += "undu states= %s" % " ".join(map(str, self.ds.UndulatorStates))

        return info_str
