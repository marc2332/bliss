# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState, NoSettingsAxis
from bliss.common.tango import DevState, DeviceProxy
from bliss.common.logtools import log_debug
from bliss.common.utils import object_attribute_get, object_attribute_set
from bliss.common.utils import object_method


# NoSettingsAxis does not use cache for settings
# -> force to re-read velocity/position at each usage.
Axis = NoSettingsAxis


class ESRF_Undulator(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.axis_info = {}

        try:
            self.ds_name = self.config.get("ds_name")
        except Exception:
            log_debug(
                self, "no 'ds_name' defined in config for %s" % self.config.get("name")
            )

    """
    Controller initialization actions.
    """

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

        # Get a proxy on Insertion Device device server of the beamline.
        self.device = DeviceProxy(self.ds_name)

    """
    Axes initialization actions.
    """

    def initialize_axis(self, axis):
        try:
            attr_pos_name = axis.config.get("attribute_position", str)
        except KeyError:
            attr_pos_name = "Position"

        log_debug(self, f"attr_pos_name={attr_pos_name}")

        try:
            attr_vel_name = axis.config.get("attribute_velocity", str)
        except KeyError:
            attr_vel_name = "Velocity"
        log_debug(self, f"attr_vel_name={attr_vel_name}")

        try:
            attr_fvel_name = axis.config.get("attribute_first_velocity", str)
        except KeyError:
            attr_fvel_name = "FirstVelocity"

        log_debug(self, f"attr_fvel_name={attr_fvel_name}")

        try:
            attr_acc_name = axis.config.get("attribute_acceleration", str)
        except KeyError:
            attr_acc_name = "Acceleration"

        log_debug(self, f"attr_acc_name={attr_acc_name}")

        alpha = axis.config.get("alpha", float, 0.0)
        period = axis.config.get("period", float, 0.0)

        log_debug(self, f"alpha={alpha}  period={period}")

        try:
            undu_prefix = axis.config.get("undu_prefix", str)
        except KeyError:
            log_debug(self, "'undu_prefix' not specified in config")
            if attr_pos_name == "Position":
                raise RuntimeError("'undu_prefix' must be specified in config")
            else:
                undu_prefix = ""

        # check for revolver undulator
        is_revolver = False
        undulator_index = None
        disabled = False
        pos = attr_pos_name.find("_")
        uname = attr_pos_name[0:pos]
        uname = uname.lower()
        # NB: "UndulatorNames" return list of names but not indexed properly :(
        uname_list = [item.lower() for item in self.device.UndulatorNames]
        undulator_index = uname_list.index(uname)
        #  "UndulatorRevolverCarriage" return an array of booleans.
        if self.device.UndulatorRevolverCarriage[undulator_index]:
            is_revolver = True
            ustate_list = self.device.UndulatorStates
            disabled = ustate_list[undulator_index] == DevState.DISABLE

        self.axis_info[axis] = {
            "is_revolver": is_revolver,
            "undulator_index": undulator_index,
            "disabled": disabled,
            "attr_pos_name": undu_prefix + attr_pos_name,
            "attr_vel_name": undu_prefix + attr_vel_name,
            "attr_fvel_name": undu_prefix + attr_fvel_name,
            "attr_acc_name": undu_prefix + attr_acc_name,
            "alpha": alpha,
            "period": period,
        }

        log_debug(self, "OK: axis well initialized")

    """
    Actions to perform at controller closing.
    """

    def finalize(self):
        pass

    def _set_attribute(self, axis, attribute_name, value):
        if self.axis_info[axis]["disabled"]:
            raise RuntimeError("Revolver axis is disabled.")
        self.device.write_attribute(self.axis_info[axis][attribute_name], value)

    def _get_attribute(self, axis, attribute_name):
        if self.axis_info[axis]["disabled"]:
            raise RuntimeError("Revolver axis is disabled.")
        return self.device.read_attribute(self.axis_info[axis][attribute_name]).value

    def start_one(self, motion, t0=None):
        self._set_attribute(
            motion.axis,
            "attr_pos_name",
            float(motion.target_pos / motion.axis.steps_per_unit),
        )

    @object_method
    def enable(self, axis):
        """ Enable the undulator axis when it is a disabled revolver axis.
        """
        axis_info = self.axis_info[axis]
        undulator_index = axis_info["undulator_index"]

        # check that the axe is a revolver axe
        if not axis_info["is_revolver"]:
            raise ValueError(f"{axis.name} is not a revolver axis")

        # check axis is disabled
        ustate_list = self.device.UndulatorStates
        if ustate_list[undulator_index] != DevState.DISABLE:
            raise ValueError(f"{axis.name} is already enabled")

        # send the Enable command
        uname = self.device.UndulatorNames[undulator_index]
        self.device.Enable(uname)

        ustate = DevState.DISABLE
        # wait for state to be neither disable nor moving
        while ustate in (DevState.DISABLE, DevState.MOVING):
            ustate = self.device.UndulatorStates[undulator_index]
            time.sleep(1)

        return axis.hw_state

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

    def __info__(self):
        info_str = f"UNDU DEVICE SERVER: {self.ds_name} \n"
        info_str += f"     status = {str(self.device.status()).strip()}\n"
        info_str += f"     state = {self.device.state()}\n"
        info_str += (
            f"     Power = {self.device.Power:.3g} (max: {self.device.MaxPower:.3g})\n"
        )
        info_str += f"     PowerDensity = {self.device.PowerDensity:.3g}  (max: {self.device.MaxPowerDensity:.3g})\n"
        return info_str

    def get_axis_info(self, axis):
        """ Return axis info specific to an undulator"""
        info_str = "TANGO DEVICE SERVER VALUES:\n"

        position = getattr(self.device, self.axis_info[axis].get("attr_pos_name"))
        info_str += (
            f"     {self.axis_info[axis].get('attr_pos_name')} = {position} mm\n"
        )

        velocity = getattr(self.device, self.axis_info[axis].get("attr_vel_name"))
        info_str += (
            f"     {self.axis_info[axis].get('attr_vel_name')} = {velocity} mm/s\n"
        )

        first_vel = getattr(self.device, self.axis_info[axis].get("attr_fvel_name"))
        info_str += (
            f"     {self.axis_info[axis].get('attr_fvel_name')} = {first_vel} mm/s\n"
        )

        acceleration = getattr(self.device, self.axis_info[axis].get("attr_fvel_name"))
        info_str += f"     {self.axis_info[axis].get('attr_acc_name')} = {acceleration} mm/s/s\n"

        info_str += "UNDU SPECIFIC INFO:\n"
        info_str += f"     config alpha: {self.axis_info[axis].get('alpha')}\n"
        info_str += f"     config period: {self.axis_info[axis].get('period')}\n"

        return info_str
