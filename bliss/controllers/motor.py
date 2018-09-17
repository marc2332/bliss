# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import functools
from bliss.common.motor_config import StaticConfig
from bliss.common.motor_settings import (
    ControllerAxisSettings,
    setting_update_from_channel,
    floatOrNone,
)
from bliss.common.axis import Axis, NoSettingsAxis, AxisRef, Trajectory
from bliss.common.motor_group import Group, TrajectoryGroup
from bliss.common import event
from bliss.physics import trajectory
from bliss.common.utils import set_custom_members, object_method
from bliss.config.channels import Cache, Channel
from bliss.config import static, settings
from gevent import lock

# make the link between encoder and axis, if axis uses an encoder
# (only 1 encoder per axis of course)
ENCODER_AXIS = dict()

# apply settings or config parameters
def get_setting_or_config_value(axis, name):
    converter = axis.settings.convert_func(name)
    value = axis.settings.get(name)
    if value is None:
        try:
            value = axis.config.get(name, converter)
        except:
            return None
    return value


class Controller(object):
    """
    Motor controller base class

    See Also:
        :ref:`bliss-how-to-motor-controller`
    """

    def __init__(self, name, config, axes, encoders, shutters, switches):
        self.__name = name
        self.__config = StaticConfig(config)
        self.__initialized_hw = Cache(self, "initialized", default_value=False)
        self.__initialized_hw_axis = dict()
        self.__initialized_encoder = dict()
        self.__initialized_axis = dict()
        self.__lock = lock.RLock()  # Semaphore()
        self._axes = dict()
        self._encoders = dict()
        self._shutters = dict()
        self._switches = dict()
        self._tagged = dict()

        self.axis_settings = ControllerAxisSettings()

        for axis_name, axis_class, axis_config in axes:
            axis = axis_class(axis_name, self, axis_config)
            self._axes[axis_name] = axis
            axis_tags = axis_config.get("tags")
            if axis_tags:
                for tag in axis_tags.split():
                    self._tagged.setdefault(tag, []).append(axis)

            # For custom attributes and commands.
            # NB : AxisRef has no controller.
            if not isinstance(axis, AxisRef):
                set_custom_members(self, axis, axis.controller._initialize_axis)

        for encoder_name, encoder_class, encoder_config in encoders:
            encoder = encoder_class(encoder_name, self, encoder_config)
            self._encoders[encoder_name] = encoder

        for obj_config_list, object_dict in (
            (shutters, self._shutters),
            (switches, self._switches),
        ):
            for obj_name, obj_class, obj_config in obj_config_list:
                if obj_class is None:
                    raise ValueError("Missing **class** for '%s`" % obj_name)
                object_dict[obj_name] = obj_class(obj_name, self, obj_config)

    def _init(self):
        controller_axes = [
            (axis_name, axis)
            for axis_name, axis in self.axes.iteritems()
            if not isinstance(axis, AxisRef)
        ]
        self._update_refs()
        self._init_settings()
        self.initialize()

        for axis_name, axis in controller_axes:
            axis_initialized = Cache(axis, "initialized", default_value=0)
            self.__initialized_hw_axis[axis] = axis_initialized
            self.__initialized_axis[axis] = False
            encoder = axis.config.get("encoder", str, "")
            if encoder:
                encoder_name = encoder.lstrip("$")
                ENCODER_AXIS[encoder_name] = axis.name

    @property
    def axes(self):
        return self._axes

    @property
    def encoders(self):
        return self._encoders

    @property
    def shutters(self):
        return self._shutters

    def get_shutter(self, name):
        return self._shutters[name]

    @property
    def switches(self):
        return self._switches

    def get_switch(self, name):
        return self._switches[name]

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    def _update_refs(self):
        config = static.get_config()
        for tag, axis_list in self._tagged.iteritems():
            for i, axis in enumerate(axis_list):
                if not isinstance(axis, AxisRef):
                    continue
                referenced_axis = config.get(axis.name)
                if not isinstance(referenced_axis, Axis):
                    raise TypeError(
                        "%s: invalid axis '%s`, not an Axis" % (self.name, axis.name)
                    )
                self.axes[axis.name] = referenced_axis
                axis_list[i] = referenced_axis

    def _init_settings(self):
        for axis in self.axes.itervalues():
            axis._beacon_channels.clear()
            hash_setting = settings.HashSetting("axis.%s" % axis.name)

            for setting_name in axis.settings:
                setting_value = get_setting_or_config_value(axis, setting_name)
                if setting_value is not None:
                    # write setting to cache
                    hash_setting[setting_name] = setting_value

                chan_name = "axis.%s.%s" % (axis.name, setting_name)
                cb = functools.partial(
                    setting_update_from_channel, setting_name=setting_name, axis=axis
                )
                if setting_value is None:
                    chan = Channel(chan_name, callback=cb)
                else:
                    chan = Channel(chan_name, default_value=setting_value, callback=cb)
                chan._setting_update_cb = cb
                axis._beacon_channels[setting_name] = chan

    def _check_limits(self, axis, user_positions):
        min_pos = user_positions.min()
        max_pos = user_positions.max()
        ll, hl = axis.limits()
        if min_pos < ll:
            # get motion object, this will raise ValueError exception
            axis._get_motion(min_pos)
        elif max_pos > hl:
            # get motion object, this will raise ValueError exception
            axis._get_motion(max_pos)

    def initialize(self):
        pass

    def initialize_hardware(self):
        """
        This method should contain all commands needed to initialize the controller hardware.
        i.e: reset, power on....
    	This initialization will be called once (by the first client).
        """
        pass

    def finalize(self):
        pass

    def _initialize_encoder(self, encoder):
        if not self.__initialized_encoder.get(encoder):
            self.initialize_encoder(encoder)
            self.__initialized_encoder[encoder] = True

    def _initialize_axis(self, axis, *args, **kwargs):
        with self.__lock:
            if self.__initialized_axis[axis]:
                return

            if not self.__initialized_hw.value:
                self.initialize_hardware()
                self.__initialized_hw.value = True

            self.initialize_axis(axis)

            axis_initialized = self.__initialized_hw_axis[axis]
            if not axis_initialized.value:
                self.initialize_hardware_axis(axis)
                axis_initialized.value = 1

            self.__initialized_axis[axis] = True

        if isinstance(axis, NoSettingsAxis):
            return

        try:
            for setting_name in axis.settings.config_settings():
                # check if setting is in config
                if axis.config.get(setting_name) is None:
                    raise RuntimeError(
                        "Axis %s: missing configuration key '%s`"
                        % (axis.name, setting_name)
                    )
                # check if setting has a method to initialize (set) its value
                try:
                    getattr(axis, setting_name)
                except AttributeError:
                    raise RuntimeError(
                        "Axis %s: missing method '%s` to set setting value"
                        % (axis.name, setting_name)
                    )

            for setting_name in axis.settings.config_settings():
                value = get_setting_or_config_value(axis, setting_name)
                meth = getattr(axis, setting_name)
                meth(value)

            low_limit = get_setting_or_config_value(axis, "low_limit")
            high_limit = get_setting_or_config_value(axis, "high_limit")
            axis.limits(low_limit, high_limit)
        except:
            self.__initialized_axis[axis] = False
            raise

    def get_axis(self, axis_name):
        axis = self._axes[axis_name]

        return axis

    def initialize_axis(self, axis):
        raise NotImplementedError

    def initialize_hardware_axis(self, axis):
        """
        This method should contain all commands needed to initialize the hardware for this axis.
        i.e: power, closed loop configuration...
    	This initialization will call only once (by the first client).
        """
        pass

    def finalize_axis(self, axis):
        raise NotImplementedError

    def get_encoder(self, encoder_name):
        encoder = self._encoders[encoder_name]

        return encoder

    def get_class_name(self):
        return self.__class__.__name__

    def initialize_encoder(self, encoder):
        raise NotImplementedError

    def has_trajectory(self):
        """
        should return True if trajectory is available
        on this controller.
        """
        return False

    def has_trajectory_event(self):
        return False

    def _prepare_trajectory(self, *trajectories):
        for traj in trajectories:
            if traj.has_events() and not self.has_trajectory_event():
                raise NotImplementedError(
                    "Controller does not support trajectories with events"
                )
        else:
            self.prepare_trajectory(*trajectories)
            if self.has_trajectory_event():
                self.set_trajectory_events(*trajectories)

    def prepare_trajectory(self, *trajectories):
        pass

    def prepare_move(self, motion):
        return

    def start_jog(self, velocity, direction):
        raise NotImplementedError

    def start_one(self, motion):
        raise NotImplementedError

    def start_all(self, *motion_list):
        raise NotImplementedError

    def move_to_trajectory(self, *trajectories):
        """
        Should go move to the first point of the trajectory
        """
        raise NotImplementedError

    def start_trajectory(self, *trajectories):
        """
        Should move to the last point of the trajectory
        """
        raise NotImplementedError

    def set_trajectory_events(self, *trajectories):
        """
        Should set trigger event on trajectories.
        Each trajectory define .events_positions or events_pattern_positions.
        """
        raise NotImplementedError

    def stop(self, axis):
        raise NotImplementedError

    def stop_jog(self, axis):
        return self.stop(axis)

    def stop_all(self, *motions):
        raise NotImplementedError

    def stop_trajectory(self, *trajectories):
        raise NotImplementedError

    def state(self, axis):
        raise NotImplementedError

    def get_info(self, axis):
        raise NotImplementedError

    def get_id(self, axis):
        raise NotImplementedError

    def raw_write(self, com):
        raise NotImplementedError

    def raw_write_read(self, com):
        raise NotImplementedError

    def home_search(self, axis, switch):
        raise NotImplementedError

    def home_state(self, axis):
        raise NotImplementedError

    def limit_search(self, axis, limit):
        raise NotImplementedError

    def read_position(self, axis):
        raise NotImplementedError

    def set_position(self, axis, new_position):
        raise NotImplementedError

    def read_encoder(self, encoder):
        """
        Returns the encoder value in *encoder steps*.
        """
        raise NotImplementedError

    def set_encoder(self, encoder, new_value):
        """
        Sets encoder value. <new_value> is in encoder steps.
        """
        raise NotImplementedError

    def read_velocity(self, axis):
        raise NotImplementedError

    def set_velocity(self, axis, new_velocity):
        raise NotImplementedError

    def set_on(self, axis):
        raise NotImplementedError

    def set_off(self, axis):
        raise NotImplementedError

    def read_acceleration(self, axis):
        raise NotImplementedError

    def set_acceleration(self, axis, new_acc):
        raise NotImplementedError

    def set_event_positions(self, axis_or_encoder, positions):
        """
        This method is use to load into the controller
        a list of positions for event/trigger.
        The controller should generate an event
        (mainly electrical pulses) when the axis or
        the encoder pass through one of this position.
        """
        raise NotImplementedError

    def get_event_positions(self, axis_or_encoder):
        """
        @see set_event_position
        """
        raise NotImplementedError


class CalcController(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False

        self._reals_group = None
        self.reals = []
        self.pseudos = []

    def initialize(self):
        for real_axis in self._tagged["real"]:
            # check if real axis is really from another controller
            if real_axis.controller == self:
                raise RuntimeError("Real axis '%s` doesn't exist" % real_axis.name)
            self.reals.append(real_axis)

        self.pseudos = [
            axis for axis_name, axis in self.axes.iteritems() if axis not in self.reals
        ]

        self._reals_group = Group(*self.reals)
        event.connect(self._reals_group, "move_done", self._real_move_done)

        for pseudo_axis in self.pseudos:
            event.connect(pseudo_axis, "sync_hard", self._pseudo_sync_hard)

        for real_axis in self.reals:
            event.connect(real_axis, "internal_position", self._calc_from_real)
            event.connect(real_axis, "internal__set_position", self._real_setpos_update)

    def close(self):
        event.disconnect(self._reals_group, "move_done", self._real_move_done)
        for pseudo_axis in self.pseudos:
            event.disconnect(pseudo_axis, "sync_hard", self._pseudo_sync_hard)

        for real_axis in self.reals:
            event.disconnect(real_axis, "internal_position", self._calc_from_real)
            event.disconnect(
                real_axis, "internal__set_position", self._real_setpos_update
            )

        self._reals_group = None
        self.reals = []
        self.pseudos = []

    def initialize_axis(self, axis):
        pass

    def initialize_hardware_axis(self, axis):
        if self.read_position(axis) is None:
            self._calc_from_real()

    def _pseudo_sync_hard(self):
        for real_axis in self.reals:
            real_axis.sync_hard()

    def _axis_tag(self, axis):
        return [
            tag
            for tag, axes in self._tagged.iteritems()
            if tag != "real" and len(axes) == 1 and axis in axes
        ][0]

    def _get_set_positions(self):
        setpos_dict = dict()
        for axis in self.pseudos:
            setpos_dict[self._axis_tag(axis)] = axis.user2dial(axis._set_position())
        return setpos_dict

    def _real_setpos_update(self, _):
        real_setpos = dict()
        for axis in self.reals:
            real_setpos[self._axis_tag(axis)] = axis._set_position()

        new_setpos = self.calc_from_real(real_setpos)

        for tagged_axis_name, setpos in new_setpos.iteritems():
            axis = self._tagged[tagged_axis_name][0]
            axis.settings.set("_set_position", axis.dial2user(setpos))

    def _check_limits(self, axis, positions):
        return
        assert axis not in self.reals
        assert axis in self.pseudos

        pseudo_axis_tag = self._axis_tag(axis)

        axis_positions = self._get_set_positions()
        for ptag, ppos in axis_positions.iteritems():
            if ptag == pseudo_axis_tag:
                axis_positions[ptag] = positions
            else:
                axis_positions[ptag] = numpy.full_like(positions, ppos)

        real_positions = self.calc_to_real(axis_positions)

        for rtag, rpos in real_positions.iteritems():
            real_axis = self._tagged[rtag][0]
            real_axis.controller._check_limits(real_axis, rpos)

    def _do_calc_from_real(self):
        real_positions_by_axis = self._reals_group.position()
        real_positions = dict(
            [
                (self._axis_tag(axis), pos)
                for axis, pos in real_positions_by_axis.items()
            ]
        )
        return self.calc_from_real(real_positions)

    def _calc_from_real(self, *args, **kwargs):
        new_positions = self._do_calc_from_real()

        for tagged_axis_name, dial_pos in new_positions.iteritems():
            axis = self._tagged[tagged_axis_name][0]
            if axis in self.pseudos:
                user_pos = axis.dial2user(dial_pos)
                axis.settings.set("dial_position", dial_pos)
                axis.settings.set("position", user_pos)
            else:
                raise RuntimeError("cannot assign position to real motor")
        return new_positions

    def calc_from_real(self, real_positions):
        """Return a dict { pseudo motor tag: new position, ... }"""
        raise NotImplementedError

    def _real_move_done(self, done):
        if done:
            for axis in self.pseudos:
                if axis.encoder:
                    # check position and raise RuntimeError if encoder
                    # position doesn't correspond to axis position
                    # (MAXE_E)
                    axis._do_encoder_reading()

    def start_one(self, motion):
        self.start_all(motion)

    def start_all(self, *motion_list):
        positions_dict = self._get_set_positions()
        move_dict = dict()
        for tag, target_pos in self.calc_to_real(positions_dict).iteritems():
            real_axis = self._tagged[tag][0]
            move_dict[real_axis] = target_pos

        # force a global position update in case phys motors never move
        self._calc_from_real()
        self._reals_group.move(move_dict, wait=False)

    def calc_to_real(self, positions_dict):
        raise NotImplementedError

    def stop(self, axis):
        self._reals_group.stop()

    def read_position(self, axis):
        return axis.settings.get("dial_position")

    def state(self, axis, new_state=None):
        st = self._reals_group.state()
        if st.READY:
            self._calc_from_real()
        return st

    def set_position(self, axis, new_pos):
        if not axis in self.pseudos:
            raise RuntimeError(
                "Cannot set dial position on motor '%s` from CalcController" % axis.name
            )

        positions = self._get_set_positions()
        positions[self._axis_tag(axis)] = new_pos
        real_positions = self.calc_to_real(positions)
        for real_axis_tag, user_pos in real_positions.iteritems():
            self._tagged[real_axis_tag][0].position(user_pos)

        new_positions = self._calc_from_real()

        return new_positions[self._axis_tag(axis)]

    @object_method(types_info=(("float", "float", "int", "float"), "object"))
    def scan_on_trajectory(
        self,
        calc_axis,
        start_point,
        end_point,
        nb_points,
        time_per_point,
        interpolation_factor=1,
    ):
        """
        helper to create a trajectories handler for a scan.

        It will check the **trajectory_minimum_resolution** and
        **trajectory_maximum_resolution** axis property.
        If the trajectory resolution asked is lower than the trajectory_minimum_resolution,
        the trajectory will be over sampled.
        And if the trajectory resolution asked is higher than the trajectory_maximum_resolution
        the trajectory will be down sampled.
        Args:
            start -- first point of the trajectory
            end -- the last point of the trajectory
            nb_points -- the number of point created for this trajectory
            time_per_point -- the time between each points.
        """
        # check if real motor has trajectory capability
        real_axes = list()
        real_involved = self.calc_to_real(
            {self._axis_tag(caxis): caxis.position() for caxis in self.pseudos}
        )
        for real in self.reals:
            if self._axis_tag(real) in real_involved:
                axis, raxes = self._check_trajectory(real)
                real_axes.append((axis, raxes))

        trajectory_minimum_resolution = calc_axis.config.get(
            "trajectory_minimum_resolution", floatOrNone, None
        )
        trajectory_maximum_resolution = calc_axis.config.get(
            "trajectory_maximum_resolution", floatOrNone, None
        )

        # Check if the resolution is enough
        total_distance = abs(end_point - start_point)
        trajectory_resolution = total_distance / float(nb_points)
        used_resolution = None

        if (
            trajectory_minimum_resolution is not None
            and trajectory_maximum_resolution is not None
        ):
            if not (
                trajectory_maximum_resolution
                >= trajectory_resolution
                >= trajectory_minimum_resolution
            ):
                if trajectory_resolution > trajectory_minimum_resolution:
                    used_resolution = trajectory_minimum_resolution
                else:
                    used_resolution = trajectory_maximum_resolution
        elif trajectory_minimum_resolution is not None:
            if trajectory_resolution > trajectory_minimum_resolution:
                used_resolution = trajectory_minimum_resolution
        elif trajectory_maximum_resolution is not None:
            if trajectory_resolution < trajectory_maximum_resolution:
                used_resolution = trajectory_maximum_resolution

        if used_resolution is not None:
            new_nb_points = int(round(total_distance / used_resolution))
            new_time_point = float(time_per_point * nb_points) / new_nb_points
            nb_points = new_nb_points
            time_per_point = new_time_point

        calc_positions = numpy.linspace(start_point, end_point, nb_points)
        positions = {self._axis_tag(calc_axis): calc_positions}
        # other virtual axis stays at the same position
        for caxis in self.pseudos:
            if caxis is calc_axis:
                continue
            cpos = numpy.zeros(len(calc_positions), dtype=numpy.float)
            cpos[:] = caxis.position()
            positions[self._axis_tag(caxis)] = cpos

        time = numpy.linspace(0., nb_points * time_per_point, nb_points)
        real_positions = self.calc_to_real(positions)
        final_real_axes_position = dict()
        self._get_real_position(real_axes, real_positions, final_real_axes_position)

        pt = trajectory.PointTrajectory()
        spline_nb_points = (
            0 if interpolation_factor == 1 else len(time) * interpolation_factor
        )
        pt.build(
            time,
            {
                axis.name: position
                for axis, position in final_real_axes_position.iteritems()
            },
            spline_nb_points=spline_nb_points,
        )
        # check velocity and acceleration
        max_velocity = pt.max_velocity()
        max_acceleration = pt.max_acceleration()
        limits = pt.limits()
        error_list = list()
        start_stop_acceleration = dict()
        for axis in final_real_axes_position:
            vel = axis.velocity()
            acc = axis.acceleration()
            axis_limits = axis.limits()
            traj_vel = max_velocity[axis.name]
            traj_acc = max_acceleration[axis.name]
            traj_limits = limits[axis.name]
            if traj_acc > acc:
                error_list.append(
                    "Axis %s reach %f acceleration on this trajectory,"
                    "max acceleration is %f" % (axis.name, traj_acc, acc)
                )
            if traj_vel > vel:
                error_list.append(
                    "Axis %s reach %f velocity on this trajectory,"
                    "max velocity is %f" % (axis.name, traj_vel, vel)
                )
            for lm in traj_limits:
                if not axis_limits[0] <= lm <= axis_limits[1]:
                    error_list.append(
                        "Axis %s go beyond limits (%f <= %f <= %f)"
                        % (axis.name, axis_limits[0], traj_limits[0], axis_limits[1])
                    )

            start_stop_acceleration[axis.name] = acc

        if error_list:
            error_message = (
                "Trajectory on calc axis **%s** can not be done.\n" % calc_axis.name
            )
            error_message += "\n".join(error_list)
            raise ValueError(error_message)

        pvt = pt.pvt(acceleration_start_end=start_stop_acceleration)
        trajectories = [
            Trajectory(axis, pvt[axis.name]) for axis in final_real_axes_position
        ]

        return TrajectoryGroup(*trajectories, calc_axis=calc_axis)

    def _check_trajectory(self, axis):
        if axis.controller.has_trajectory():
            return axis, []
        else:  # check if axis is part of calccontroller
            ctrl = axis.controller
            if isinstance(ctrl, CalcController):
                real_involved = ctrl.calc_to_real(
                    {ctrl._axis_tag(caxis): caxis.position() for caxis in ctrl.pseudos}
                )
                real_axes = list()
                for real in ctrl.reals:
                    if ctrl._axis_tag(real) in real_involved:
                        raxis, axes = self._check_trajectory(real)
                        real_axes.append((raxis, axes))
                return axis, real_axes
            else:
                raise ValueError(
                    "Controller for axis %s does not support "
                    "trajectories" % axis.name
                )

    def _get_real_position(self, real_axes, real_positions, final_real_axes_position):
        local_real_positions = dict()
        for axis, dep_real_axes in real_axes:
            axis_position = real_positions.get(self._axis_tag(axis))
            if not dep_real_axes:
                if axis_position is None:
                    raise RuntimeError(
                        "Could not get position " "for axis %s" % axis.name
                    )
                else:
                    final_real_axes_position[axis] = axis_position
            else:
                ctrl = axis.controller
                local_real_positions = {ctrl._axis_tag(axis): axis_position}
                for caxis in ctrl.pseudos:
                    axis_tag = ctrl._axis_tag(caxis)
                    if caxis is axis or axis_tag in local_real_positions:
                        continue
                    cpos = numpy.zeros(len(axis_position), dtype=numpy.float)
                    cpos[:] = caxis.position()
                    local_real_positions[ctrl._axis_tag(caxis)] = cpos

                dep_real_position = ctrl.calc_to_real(local_real_positions)
                ctrl._get_real_position(
                    dep_real_axes, dep_real_position, final_real_axes_position
                )
