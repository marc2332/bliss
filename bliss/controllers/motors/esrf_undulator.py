# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import numpy
import functools

from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState, NoSettingsAxis
from bliss.common.tango import DevState, DeviceProxy, AttributeProxy
from bliss.common.logtools import user_print, user_warning
from bliss.common.logtools import log_debug, disable_user_output
from bliss.common.utils import object_method
from bliss import global_map


def lazy_init(func):
    @functools.wraps(func)
    def f(self, *args, **kwargs):
        self._init()
        return func(self, *args, **kwargs)

    return f


class UndulatorAxis(NoSettingsAxis):
    def sync_hard(self):
        st = self.hw_state
        if "DISABLED" in st:
            self.settings.set("state", st)
            user_warning(f"undulator {self.name} is disabled, no position update")
        else:
            super().sync_hard()


# NoSettingsAxis does not use cache for settings
# -> force to re-read velocity/position at each usage.
Axis = UndulatorAxis


def get_all():
    """Return a list of all insertion device sevice server found in the
    global env.
    """
    try:
        return list(global_map.instance_iter("undulators"))
    except KeyError:
        # no undulator has been created yet there is nothing in map
        return []


class ESRF_Undulator(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        global_map.register(self, parents_list=["undulators"])

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
        global_map.register(
            self, parents_list=["undulators"], children_list=[self.device]
        )

    """
    Axes initialization actions.
    """

    def initialize_axis(self, axis):
        """
        Read configuration to forge tango attributes names.
        """

        attr_pos_name = axis.config.get("attribute_position", str, "Position")

        log_debug(self, f"attr_pos_name={attr_pos_name}")

        attr_vel_name = axis.config.get("attribute_velocity", str, "Velocity")
        log_debug(self, f"attr_vel_name={attr_vel_name}")

        attr_fvel_name = axis.config.get(
            "attribute_first_velocity", str, "FirstVelocity"
        )
        log_debug(self, f"attr_fvel_name={attr_fvel_name}")

        attr_acc_name = axis.config.get("attribute_acceleration", str, "Acceleration")
        log_debug(self, f"attr_acc_name={attr_acc_name}")

        alpha = axis.config.get("alpha", float, 0.0)
        period = axis.config.get("period", float, 0.0)
        log_debug(self, f"alpha={alpha}  period={period}")

        # Try to read undu_prefix or undulator_prefix in config
        undu_prefix = axis.config.get("undu_prefix", str)
        if undu_prefix is None:
            undu_prefix = axis.config.get("undulator_prefix", str)
        log_debug(self, f"(1) 'undu(lator)_prefix' in config: {undu_prefix}")

        if undu_prefix is None:
            # Ensure all attribute_position is defined in config.
            # ie: attr_pos_name =/= "Position"
            if attr_pos_name == "Position":
                raise RuntimeError("'undu_prefix' must be specified in config")
            undu_prefix = ""
        else:
            # Forge tango attributes: undu_prefix + attribute_name
            # undu_prefix must have "_" at end.
            log_debug(self, "(4) 'undu_prefix' in config is: %s", undu_prefix)
            attr_pos_name = undu_prefix + attr_pos_name
            attr_vel_name = undu_prefix + attr_vel_name
            attr_fvel_name = undu_prefix + attr_fvel_name
            attr_acc_name = undu_prefix + attr_acc_name

        # check for revolver undulator
        is_revolver = False
        undulator_index = None

        # Extract undulator name
        # U32A_GAP_position -> u32a
        pos = attr_pos_name.find("_")
        log_debug(self, f"attr_pos_name={attr_pos_name}   pos={pos}")
        uname = attr_pos_name[0:pos]
        uname = uname.lower()
        log_debug(self, f"uname={uname}")

        # NB: "UndulatorNames" return list of names but not indexed properly :(
        uname_list = [item.lower() for item in self.device.UndulatorNames]
        log_debug(self, f"uname_list={uname_list}")
        undulator_index = uname_list.index(uname)
        #  "UndulatorRevolverCarriage" return an array of booleans.
        if self.device.UndulatorRevolverCarriage[undulator_index]:
            is_revolver = True

        self.axis_info[axis] = {
            "name": uname,
            "is_revolver": is_revolver,
            "undulator_index": undulator_index,
            "attr_pos_name": attr_pos_name,
            "attr_vel_name": attr_vel_name,
            "attr_fvel_name": attr_fvel_name,
            "attr_acc_name": attr_acc_name,
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
        if "DISABLED" in self.state(axis):
            if self.axis_info[axis]["is_revolver"]:
                raise RuntimeError("Revolver axis is disabled.")
            else:
                raise RuntimeError("Undulator is disabled.")
        self.device.write_attribute(self.axis_info[axis][attribute_name], value)

    def _get_attribute(self, axis, attribute_name):
        if "DISABLED" in self.state(axis):
            if self.axis_info[axis]["is_revolver"]:
                raise RuntimeError("Revolver axis is disabled.")
            else:
                raise RuntimeError("Undulator is disabled.")
        return self.device.read_attribute(self.axis_info[axis][attribute_name]).value

    def start_one(self, motion, t0=None):
        self._set_attribute(
            motion.axis,
            "attr_pos_name",
            float(motion.target_pos / motion.axis.steps_per_unit),
        )
        log_debug(self, f"end of start {motion.axis.name}")

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
        if "DISABLED" not in self.state(axis):
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
        if self.device.state() == DevState.DISABLE:
            return numpy.nan

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
        if self.device.state() == DevState.DISABLE:
            return AxisState("DISABLED")

        undulator_index = self.axis_info[axis]["undulator_index"]
        ustate_list = self.device.UndulatorStates
        _state = ustate_list[undulator_index]

        if _state == DevState.ON:
            log_debug(self, f"{axis.name} READY")
            return AxisState("READY")
        elif _state == DevState.MOVING:
            log_debug(self, f"{axis.name} MOVING")
            return AxisState("MOVING")
        elif _state == DevState.DISABLE:
            log_debug(self, f"{axis.name} DISABLED")
            return AxisState("DISABLED")
        else:
            log_debug(self, f"{axis.name} READY after unknown state")
            return AxisState("READY")

    """
    POSITION
    """

    def set_position(self, axis, new_position):
        """ Implemented to avoid NotImplemented error in apply_config().
        """
        return axis.position

    """
    Must send a command to the controller to abort the motion of given axis.
    """

    def stop(self, axis):
        self.device.abort()

    def stop_all(self, *motion_list):
        self.device.abort()

    def __info__(self):
        info_str = f"\n\nUNDULATOR DEVICE SERVER: {self.ds_name} \n"
        info_str += f"     status = {str(self.device.status()).strip()}\n"
        info_str += (
            f"     Power = {self.device.Power:.3g} (max: {self.device.MaxPower:.3g})\n"
        )
        info_str += f"     PowerDensity = {self.device.PowerDensity:.3g}  (max: {self.device.MaxPowerDensity:.3g})\n"
        return info_str

    def get_axis_info(self, axis):
        """ Return axis info specific to an undulator"""
        info_str = "TANGO DEVICE SERVER VALUES:\n"

        state = self.state(axis)
        info_str += f"     state = {str(state)}\n"

        if "DISABLED" in state:
            position = "-"
            velocity = "-"
            first_vel = "-"
            acceleration = "-"
        else:
            position = getattr(self.device, self.axis_info[axis].get("attr_pos_name"))
            velocity = getattr(self.device, self.axis_info[axis].get("attr_vel_name"))
            first_vel = getattr(self.device, self.axis_info[axis].get("attr_fvel_name"))
            acceleration = getattr(
                self.device, self.axis_info[axis].get("attr_acc_name")
            )

        info_str += (
            f"     {self.axis_info[axis].get('attr_pos_name')} = {position} mm\n"
        )

        info_str += (
            f"     {self.axis_info[axis].get('attr_vel_name')} = {velocity} mm/s\n"
        )

        info_str += (
            f"     {self.axis_info[axis].get('attr_fvel_name')} = {first_vel} mm/s\n"
        )

        info_str += f"     {self.axis_info[axis].get('attr_acc_name')} = {acceleration} mm/s/s\n"

        info_str += "UNDULATOR SPECIFIC INFO:\n"
        info_str += f"     config alpha: {self.axis_info[axis].get('alpha')}\n"
        info_str += f"     config period: {self.axis_info[axis].get('period')}\n"

        return info_str

    @lazy_init
    def _test_suite(self, axis):
        """Set of tests to be used to validate the behaviour of an undulator.
        * at max speed
        *   very long moves ~100 mm
        *   moves (10mm)
        *   small moves (1mm)
        *   very small moves (10 um)

        Usage example: u55a.controller._test_suite(u55a)
        """

        attr_pos_uri = self.ds_name + "/" + self.axis_info[axis]["attr_pos_name"]
        attr_pos = AttributeProxy(attr_pos_uri)
        # user_print(attr_pos.get_config())

        # min max values can be : 'Not specified'
        try:
            small_gap = float(attr_pos.get_config().min_value) + 2.0
        except ValueError:
            small_gap = 15
        try:
            large_gap = float(attr_pos.get_config().max_value / 2.0)
        except ValueError:
            large_gap = 50

        user_print("\nUndulator test suite \n")
        user_print("Will use following value:")
        user_print(f"  small gap = {small_gap}")
        user_print(f"  large gap = {large_gap}")
        user_print("\n")

        max_velocity = 5
        user_print(f"set velocity to {max_velocity}mm/s")
        axis.velocity = max_velocity

        user_print(f"move to small gap ({small_gap}mm)")
        axis.move(small_gap)

        # long move at full speed
        user_print(f"move to large gap ({large_gap})")
        axis.move(large_gap)

        test_movements = [
            {"desc": "10um", "dist_mm": 0.01, "nb_moves": 25},
            {"desc": "1mm", "dist_mm": 1, "nb_moves": 15},
            {"desc": "10mmm", "dist_mm": 10, "nb_moves": 5},
        ]

        user_print(" LARGE GAP--------------")
        for tm in test_movements:
            user_print(f"     {tm['nb_moves']} {tm['desc']} movements")
            nb_moves = tm["nb_moves"]
            dist_mm = tm["dist_mm"]
            for ii in range(nb_moves):
                user_print(f"\r {ii}/{nb_moves} ", end="")
                with disable_user_output():
                    axis.move(dist_mm, relative=True)
                    axis.move(-dist_mm, relative=True)

        user_print(f"move to small gap ({small_gap}mm)")
        axis.move(small_gap)
        user_print(" SMALL GAP--------------")

        for tm in test_movements:
            user_print(f"     {tm['nb_moves']} {tm['desc']} movements")
            nb_moves = tm["nb_moves"]
            dist_mm = tm["dist_mm"]
            for ii in range(nb_moves):
                user_print(f"\r {ii}/{nb_moves} ", end="")
                with disable_user_output():
                    axis.move(dist_mm, relative=True)
                    axis.move(-dist_mm, relative=True)

        user_print(f"moving to large gap ({large_gap})")
        user_print("now you can test double Ctrl-C")
        axis.move(large_gap)
