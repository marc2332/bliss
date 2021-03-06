# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools
import hashlib
import numpy
from unittest import mock
from bliss.config import settings
from bliss.common.axis import NoSettingsAxis, lazy_init, DEFAULT_POLLING_TIME
from bliss.controllers.motors.icepap.comm import _command, _vdata_header

PARAMETER, POSITION, SLOPE = (0x1000, 0x2000, 0x4000)


def check_initialized(func):
    @functools.wraps(func)
    def func_wrapper(self, *args, **kwargs):
        if self._axes is None:
            raise RuntimeError(
                "Axis ** %s ** not initialized, " "hint: call set_positions" % self.name
            )
        return func(self, *args, **kwargs)

    return func_wrapper


class TrajectoryAxis(NoSettingsAxis):
    """
    Virtual Icepap axis with follow a trajectory defined by
    a position table.
    You need to load a trajectory table with method
    **set_positions** before using the axis.
    """

    SPLINE, LINEAR, CYCLIC = list(range(3))

    def __init__(self, name, controller, config):
        controller.axis_settings.config_setting["acceleration"] = False
        controller.axis_settings.config_setting["velocity"] = False

        super().__init__(name, controller, config)

        self._axes = None
        self._parameter = None
        self._positions = None
        self._trajectory_mode = TrajectoryAxis.SPLINE
        self._disabled_axes = set()
        self._hash_cache = dict()

        self.auto_join_trajectory = config.get("auto_join_trajectory", "True")
        self._config_velocity = -1  # auto max vel on the trajectory
        self._config_acceleration = -1  # auto max acceleration for motors involved
        self._velocity = -1
        self._acceleration_time = -1

    @property
    def no_offset(self):
        return True

    @property
    def disabled_axes(self):
        """
        Axes which motion are disabled.
        """
        return self._disabled_axes

    def disable_axis(self, axis):
        """
        Disable motion of a real axis.
        """
        self._disabled_axes.add(axis)

    def show(self):
        print("")
        print("ENABLED :  ", end="")
        for m in self.enabled_axes:
            print("%s" % m.name, end=" ")
        print("")
        print("DISABLED:  ", end="")
        for m in self.disabled_axes:
            print("%s" % m.name, end=" ")
        print("")

    @property
    def enabled_axes(self):
        """
        Axes which motion are enabled.
        """
        return set(self.real_axes) - self.disabled_axes

    def enable_axis(self, axis):
        """
        Enable motion of a real axis.
        """
        try:
            self._disabled_axes.remove(axis)
        except KeyError:
            pass

    @lazy_init
    def set_positions(self, parameter, positions, trajectory_mode=SPLINE):
        """
        Set the real axes positions for this virtual motor.

        Args:
            parameter: apse of all real motor positions
            positions: a dictionary with the key as the name of the
            motor and with the value as the position of this motor.
            trajectory_mode: default is SPLINE but could be CYCLIC or LINEAR
        """
        axes = dict()
        for name, axis in self.controller.axes.items():
            if name in positions:
                axes[axis.name] = axis
                positions[axis.name] *= axis.steps_per_unit
        if len(positions) > len(axes):
            raise RuntimeError(
                "Axis %s, real axes (%s) are not "
                "managed in this controller"
                % (self.name, ",".join(set(positions) - set(axes)))
            )
        self._hash_cache = dict()
        self._trajectory_mode = trajectory_mode
        self._load_trajectories(axes, parameter, positions)
        self._axes = axes
        self._disabled_axes = set()
        self._parameter = parameter
        self._positions = positions
        self._set_velocity(self._config_velocity)
        self._set_acceleration_time(self._config_acceleration)

    def get_positions(self):
        """
        Positions of all real axes
        """
        return self._parameter, self._positions

    @property
    @check_initialized
    def real_motor_names(self):
        """
        Return a list of real motor linked to this virtual axis
        """
        return list(self._axes.keys())

    @property
    @check_initialized
    def real_axes(self):
        """
        Return a list of real axis linked to this virtual axis
        """
        return list(self._axes.values())

    @check_initialized
    def movep(
        self,
        user_target_pos,
        wait=True,
        relative=False,
        polling_time=DEFAULT_POLLING_TIME,
    ):
        """
        movement to parameter value
        """
        # check if trajectories are loaded
        self._load_trajectories(self._axes, self._parameter, self._positions)
        axes_str = " ".join(("%s" % axis.address for axis in self.enabled_axes))
        motion = self.prepare_move(user_target_pos, relative)

        def start_one(controller, motions):
            _command(
                controller._cnx, "#MOVEP {} {}".format(motions[0].target_pos, axes_str)
            )

        def stop_one(controller, motions):
            controller.stop(motions[0].axis)

        self._group_move.move(
            {self.controller: [motion]},
            start_one,
            stop_one,
            wait=False,
            polling_time=polling_time,
        )

        if wait:
            self.wait_move()

    def _init_software(self):
        try:
            self._config_velocity = self.config.get("velocity", float)
        except KeyError:
            self.config.set("velocity", -1)  # maximum for a trajectory

        try:
            self._config_acceleration = self.config.get("acceleration", float)
        except KeyError:
            # maximum accelaration for motor involved
            self.config.set("acceleration", -1)

    def _load_trajectories(self, axes, parameter, positions):
        data = numpy.array([], dtype=numpy.int8)
        update_cache = list()

        # set trajectory mode
        t_mode = {
            TrajectoryAxis.LINEAR: "LINEAR",
            TrajectoryAxis.SPLINE: "SPLINE",
            TrajectoryAxis.CYCLIC: "CYCLIC",
        }
        t_mode_str = t_mode.get(self._trajectory_mode)

        # check memory
        # memory_max = int(self.controller.raw_write("0:?memory").split(" ")[2])
        # limited to 400000 due to the timeout on the icepap DSP
        # memory_max = 390000
        memory_max = 300000

        # build parameter table
        param_data = _vdata_header(parameter, self, PARAMETER, addr="255")
        data = numpy.append(data, param_data)

        # build axis table
        table_length_test_done = False
        at_least_one_axis_to_load = False
        axis_name_list = ""
        for mot_name, pos in positions.items():
            axis = axes[mot_name]
            if axis._trajectory_cache.value == self._hash_cache.get(
                mot_name, numpy.nan
            ):
                continue

            axis_data = _vdata_header(pos, axis, POSITION)

            if not table_length_test_done:
                table_length_test_done = True
                if (axis_data.size + param_data.size) > memory_max:
                    raise RuntimeError(
                        "Axis %s: trajectory table too long (%d byte) for icepap memory (%d byte)"
                        % (self.name, axis_data.size + param_data.size, memory_max)
                    )

            if (data.size + axis_data.size) > memory_max:
                # print("Sending trajectory for %s"%axis_name_list)
                _command(
                    self.controller._cnx,
                    "#*PARDAT {}".format(t_mode_str),
                    data=data,
                    timeout=30,
                )
                axis_name_list = ""
                data = numpy.array([], dtype=numpy.int8)
                data = numpy.append(data, param_data)

            axis_name_list = axis_name_list + " " + mot_name

            h = hashlib.md5()
            h.update(axis_data.tobytes())
            digest = h.hexdigest()
            if axis._trajectory_cache.value != digest:
                at_least_one_axis_to_load = True
                data = numpy.append(data, axis_data)
                update_cache.append((axis, digest))
            else:
                self._hash_cache[axis.name] = digest

        if not at_least_one_axis_to_load:  # nothing to do
            return

        # print("Send trajectory for %s (LAST)"%axis_name_list)
        _command(
            self.controller._cnx,
            "#*PARDAT {}".format(t_mode_str),
            data=data,
            timeout=15,
        )

        # update axis trajectory cache
        for axis, value in update_cache:
            axis._trajectory_cache.value = value
            self._hash_cache[axis.name] = value

    @check_initialized
    def _start_one(self, motion):
        target_pos = motion.target_pos
        # check if trajectories are loaded
        self._load_trajectories(self._axes, self._parameter, self._positions)
        axes_str = " ".join(("%s" % axis.address for axis in self.enabled_axes))
        try:
            _command(self.controller._cnx, "#PMOVE {} {}".format(target_pos, axes_str))
        except RuntimeError:
            if self.auto_join_trajectory:
                _command(
                    self.controller._cnx, "#MOVEP {} {}".format(target_pos, axes_str)
                )
            else:
                raise

    def _stop(self):
        """
        Stop all real axes
        """
        axes_str = " ".join(("%s" % axis.address for axis in self.enabled_axes))
        _command(self.controller._cnx, "STOP %s" % axes_str)

    def _get_max_velocity(self):
        max_velocity = None
        for axis in self.real_axes:
            max_axis_vel = float(
                _command(self.controller._cnx, "%d:?PARVEL max" % axis.address)
            )
            max_axis_vel = min(axis.velocity * axis.steps_per_unit, max_axis_vel)
            if max_velocity is None or max_axis_vel < max_velocity:
                max_velocity = max_axis_vel

        return max_velocity

    def _set_velocity(self, velocity):
        if self._axes:  # trajectory is already loaded
            self._load_trajectories(self._axes, self._parameter, self._positions)
            if velocity < 0:  # get the max for this trajectory
                max_velocity = None
                max_acceleration = None
                for axis in self.real_axes:
                    max_axis_vel = float(
                        _command(self.controller._cnx, "%d:?PARVEL max" % axis.address)
                    )
                    max_axis_vel = min(
                        axis.velocity * axis.steps_per_unit, max_axis_vel
                    )
                    if max_velocity is None or max_axis_vel < max_velocity:
                        max_velocity = max_axis_vel

                velocity = max_velocity
            axes_str = " ".join(("%s" % axis.address for axis in self.real_axes))
            _command(self.controller._cnx, "#PARVEL {} {}".format(velocity, axes_str))
            self._acceleration_time = float(
                _command(
                    self.controller._cnx,
                    "?PARACCT {}".format(self.real_axes[0].address),
                )
            )

        self._velocity = velocity
        return velocity

    def _get_velocity(self):
        return self._velocity

    def _get_min_acceleration_time(self):
        min_acceleration_time = None
        for axis in self.real_axes:
            axis_acceleration_time = axis.acctime
            if (
                min_acceleration_time is None
                or axis_acceleration_time > min_acceleration_time
            ):
                min_acceleration_time = axis_acceleration_time
            acceleration_time = min_acceleration_time * 1.1
        return acceleration_time

    def _set_acceleration_time(self, acceleration_time):
        if self._axes:  # trajectory is already loaded
            self._load_trajectories(self._axes, self._parameter, self._positions)
            if acceleration_time < 0:  # get the max for this trajectory
                min_acceleration_time = None
                for axis in self.real_axes:
                    axis_acceleration_time = axis.acctime
                    if (
                        min_acceleration_time is None
                        or axis_acceleration_time > min_acceleration_time
                    ):
                        min_acceleration_time = axis_acceleration_time
                # Minimum acceleration time given by each motors of a trajectory
                # may be be in certain cases to short. This implies lost of
                # steps. It never happened adding a this 10% overtime.
                acceleration_time = min_acceleration_time * 1.1
            axes_str = " ".join(("%s" % axis.address for axis in self.real_axes))
            _command(
                self.controller._cnx,
                "#PARACCT {} {}".format(acceleration_time, axes_str),
            )
        self._acceleration_time = acceleration_time
        return acceleration_time

    def _get_acceleration_time(self):
        return self._acceleration_time

    def _read_position(self):
        rposition = numpy.nan
        if self._axes:
            axes_str = " ".join(("%s" % axis.address for axis in self.enabled_axes))
            try:
                positions = _command(
                    self.controller._cnx, "?PARPOS {}".format(axes_str)
                )
            except RuntimeError:
                pass  # Parametric mode is not in sync
            else:
                positions = numpy.array([float(pos) for pos in positions.split()])
                rposition = positions.mean()
            # update real motors
            for axis in self.enabled_axes:
                axis.sync_hard()

        return rposition

    def _state(self):
        axes_str = " ".join(("%s" % axis.address for axis in self.enabled_axes))
        all_status = [
            int(s, 16)
            for s in _command(self.controller._cnx, "?FSTATUS %s" % (axes_str)).split()
        ]
        status = all_status.pop(0)
        stop_code = status & (0xf << 14)
        # test internal stop code which
        # are not relevant stop for us
        # so clear it
        if stop_code == (7 << 14) or stop_code == (14 << 14):
            status &= ~(0xf << 14)
        for axis_status in all_status:
            stop_code = axis_status & (0xf << 14)
            if stop_code == 0 or stop_code == (7 << 14) or stop_code == (14 << 14):
                status &= ~(0xf << 14)  # clear stop_code
            axis_status &= ~(0xf << 14)

            rp_status = status & (axis_status & (1 << 9 | 1 << 23))  # READY POWERON
            other_status = (status | axis_status) & ~(1 << 9 | 1 << 23)
            status = rp_status | other_status
        return status
