# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
bliss.controller.motor.EncoderCounterController
bliss.controller.motor.Controller
bliss.controller.motor.CalcController
"""

import functools
import numpy
from gevent import lock

# absolute import to avoid circular import
import bliss.common.motor_group as motor_group
from bliss.common.motor_config import MotorConfig
from bliss.common.motor_settings import ControllerAxisSettings, floatOrNone
from bliss.common.axis import Trajectory
from bliss.common import event
from bliss.controllers.counter import SamplingCounterController
from bliss.physics import trajectory
from bliss.common.utils import set_custom_members, object_method, grouped
from bliss import global_map
from bliss.config.channels import Cache

from bliss.controllers.bliss_controller import BlissController


class EncoderCounterController(SamplingCounterController):
    def __init__(self, motor_controller):
        super().__init__("encoder")

        self.motor_controller = motor_controller

        # High frequency acquisition loop
        self.max_sampling_frequency = None

    def read_all(self, *encoders):
        steps_per_unit = numpy.array([enc.steps_per_unit for enc in encoders])
        try:
            positions_array = numpy.array(
                self.motor_controller.read_encoder_multiple(*encoders)
            )
        except NotImplementedError:
            positions_array = numpy.array(
                list(map(self.motor_controller.read_encoder, encoders))
            )
        return positions_array / steps_per_unit


def check_disabled(func):
    """
    Decorator used to raise exception if accessing an attribute of a disabled
    motor controller.
    """

    @functools.wraps(func)
    def func_wrapper(self, *args, **kwargs):
        if self._disabled:
            raise RuntimeError(f"Controller is disabled. Check hardware and restart.")
        return func(self, *args, **kwargs)

    return func_wrapper


class Controller(BlissController):
    """
    Motor controller base class
    """

    def __init__(self, *args, **kwargs):  # config

        if len(args) == 1:
            config = args[0]
        else:
            # handle old signature: args = [ name, config, axes, encoders, shutters, switches ]
            config = args[1]

        super().__init__(config)

        self.__motor_config = MotorConfig(config)
        self.__initialized_hw = Cache(self, "initialized", default_value=False)
        self.__initialized_hw_axis = dict()
        self.__initialized_encoder = dict()
        self.__initialized_axis = dict()
        self.__lock = lock.RLock()
        self._encoder_counter_controller = EncoderCounterController(self)
        self._axes = dict()
        self._encoders = dict()
        self._shutters = dict()
        self._switches = dict()
        self._tagged = dict()
        self._disabled = False

        self.axis_settings = ControllerAxisSettings()
        global_map.register(self, parents_list=["controllers"])

    def _load_config(self):
        self._axes_config = {}
        self._encoders_config = {}
        self._shutters_config = {}
        self._switches_config = {}

        for k, v in self._subitems_config.items():
            cfg, pkey = v
            if pkey == "axes":
                self._axes_config[k] = cfg

            elif pkey == "encoders":
                self._encoders_config[k] = cfg

            elif pkey == "shutters":
                self._shutters_config[k] = cfg

            elif pkey == "switches":
                self._switches_config[k] = cfg

    def _get_subitem_default_module(self, class_name, cfg, parent_key):
        if parent_key == "axes":
            return "bliss.common.axis"

        elif parent_key == "encoders":
            return "bliss.common.encoder"

        elif parent_key == "shutters":
            return "bliss.common.shutter"

        elif parent_key == "switches":
            return "bliss.common.switch"

    def _get_subitem_default_class_name(self, cfg, parent_key):
        if parent_key == "axes":
            return "Axis"
        elif parent_key == "encoders":
            return "Encoder"
        elif parent_key == "shutters":
            return "Shutter"
        elif parent_key == "switches":
            return "Switch"

    @check_disabled
    def _create_subitem_from_config(
        self, name, cfg, parent_key, item_class, item_obj=None
    ):

        if parent_key == "axes":
            if item_class is None:  # it is a reference
                axis = item_obj
            else:
                axis = item_class(name, self, cfg)

            self._axes[name] = axis

            axis_tags = cfg.get("tags")
            if axis_tags:
                for tag in axis_tags.split():
                    self._tagged.setdefault(tag, []).append(axis)

            if axis.controller is self:
                set_custom_members(self, axis, self._initialize_axis)
            else:
                # reference axis
                return axis

            if axis.controller is self:
                axis_initialized = Cache(axis, "initialized", default_value=0)
                self.__initialized_hw_axis[axis] = axis_initialized
                self.__initialized_axis[axis] = False

            self._add_axis(axis)
            return axis

        elif parent_key == "encoders":
            encoder = self._encoder_counter_controller.create_counter(
                item_class, name, motor_controller=self, config=cfg
            )
            self._encoders[name] = encoder
            self.__initialized_encoder[encoder] = False
            return encoder

        elif parent_key == "switches":
            switch = item_class(name, cfg)
            self._switches[name] = switch
            return switch

        elif parent_key == "shutters":
            shutter = item_class(name, cfg)
            self._shutters[name] = shutter
            return shutter

    def _init(self):
        try:
            self.initialize()
            self._disabled = False
        except BaseException:
            self._disabled = True
            raise

    @property
    def config(self):
        return self.__motor_config

    @property
    def axes(self):
        return self._axes

    @property
    def encoders(self):
        return self._encoders

    @property
    def shutters(self):
        return self._shutters

    @property
    def switches(self):
        return self._switches

    @check_disabled
    def get_axis(self, name):
        return self._get_subitem(name)

    @check_disabled
    def get_encoder(self, name):
        return self._get_subitem(name)

    @check_disabled
    def get_shutter(self, name):
        return self._get_subitem(name)

    @check_disabled
    def get_switch(self, name):
        return self._get_subitem(name)

    def steps_position_precision(self, axis):
        """
        Return a float value representing the precision of the position in steps

        * 1e-6 is the default value: it means the motor can deal with floating point
          steps up to 6 digits
        * 1 means the motor controller can only deal with an integer number of steps
        """
        return 1e-6

    def check_limits(self, *axis_positions):
        """
        check limits for list of axis and positions
        """
        if len(axis_positions) == 1:
            # assuming axis_positions is just a grouper object with axis, positions
            for axis, positions in axis_positions[0]:
                self._check_limits(axis, positions)
        else:
            # backward compatibility
            for axis, positions in grouped(axis_positions, 2):
                self._check_limits(axis, positions)

    def _check_limits(self, axis, user_positions):
        try:
            min_pos = min(user_positions)
        except TypeError:
            min_pos = user_positions
        try:
            max_pos = max(user_positions)
        except TypeError:
            max_pos = user_positions

        ll, hl = axis.limits
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

    @check_disabled
    def encoder_initialized(self, encoder):
        return self.__initialized_encoder[encoder]

    @check_disabled
    def _initialize_encoder(self, encoder):
        with self.__lock:
            if self.__initialized_encoder[encoder]:
                return
            self.__initialized_encoder[encoder] = True
            self._initialize_hardware()

            try:
                self.initialize_encoder(encoder)
            except BaseException as enc_init_exc:
                self.__initialized_encoder[encoder] = False
                raise RuntimeError(
                    f"Cannot initialize {self.name} encoder"
                ) from enc_init_exc

    @check_disabled
    def axis_initialized(self, axis):
        return self.__initialized_axis[axis]

    def _initialize_hardware(self):
        # initialize controller hardware only once.

        if not self.__initialized_hw.value:
            try:
                self.initialize_hardware()
            except BaseException:
                self._disabled = True
                raise
            self.__initialized_hw.value = True

    @check_disabled
    def _initialize_axis(self, axis, *args, **kwargs):
        """
        Called by axis.lazy_init
        """
        with self.__lock:
            if self.__initialized_axis[axis]:
                return

            self._initialize_hardware()

            # Consider axis is initialized
            # => prevent re-entering  _initialize_axis()  in lazy_init
            self.__initialized_axis[axis] = True

            try:
                # Call specific axis initialization.
                self.initialize_axis(axis)

                # Call specific hardware axis initialization.
                # Done only once even in case of multi clients.
                axis_initialized = self.__initialized_hw_axis[axis]
                if not axis_initialized.value:
                    self.initialize_hardware_axis(axis)
                    axis.settings.check_config_settings()
                    axis.settings.init()  # get settings, from config or from cache, and apply to hardware
                    axis_initialized.value = 1

            except BaseException:
                # Failed to initialize
                self.__initialized_axis[axis] = False
                raise

    def _add_axis(self, axis):
        """
        This method is called when a new axis is attached to
        this controller.
        This is called only once per axis.
        """
        pass

    def initialize_axis(self, axis):
        raise NotImplementedError

    def initialize_hardware_axis(self, axis):
        """
        This method should contain all commands needed to initialize the
        hardware for this axis.
        i.e: power, closed loop configuration...
        This initialization will call only once (by the first client).
        """
        pass

    def finalize_axis(self, axis):
        raise NotImplementedError

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

    def prepare_all(self, *motion_list):
        raise NotImplementedError

    def prepare_move(self, motion):
        return

    def start_jog(self, axis, velocity, direction):
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

    def check_ready_to_move(self, axis, state):
        """
        method to check if the axis can move with the current state
        """
        if not state.READY and not state.MOVING:
            # read state from hardware
            state = axis.hw_state
            axis._update_settings(state=state)

        return state.READY

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
        """Set the position of <axis> in controller to <new_position>.
        This method is called by `position` property of <axis>.
        """
        raise NotImplementedError

    def read_encoder(self, encoder):
        """Return the encoder value in *encoder steps*.
        """
        raise NotImplementedError

    def read_encoder_multiple(self, *encoder):
        """Return the encoder value in *encoder steps*.
        """
        raise NotImplementedError

    def set_encoder(self, encoder, new_value):
        """Set encoder value. <new_value> is in encoder steps.
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

    def _is_already_on_position(self, axis, delta):
        """ return True if the difference between current position
            and new position (delta) is smaller than the positioning precision 
        """
        if abs(delta) < (self.steps_position_precision(axis) / 2):
            return True  # Already in position
        return False


class CalcController(Controller):
    def __init__(self, *args, **kwargs):

        self._reals_group = None
        self.reals = []
        self.pseudos = []
        self._lock = lock.RLock()
        self._in_real_pos_update = False

        super().__init__(*args, **kwargs)

        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False
        self.axis_settings.config_setting["steps_per_unit"] = False

    def _init(self):
        # As any motors can be used into a calc
        # force for all axis creation

        for axis_name in self._axes_config.keys():
            self.get_axis(axis_name)

        super()._init()

    def initialize(self):
        for real_axis in self._tagged["real"]:
            # check if real axis is really from another controller
            if real_axis.controller == self:
                raise RuntimeError("Real axis '%s` doesn't exist" % real_axis.name)
            self.reals.append(real_axis)
            event.connect(real_axis, "internal_position", self._real_position_update)
            event.connect(real_axis, "internal__set_position", self._real_setpos_update)

        self._reals_group = motor_group.Group(*self.reals)
        event.connect(self._reals_group, "move_done", self._real_move_done)
        global_map.register(self, children_list=self.reals)

    def close(self):
        event.disconnect(self._reals_group, "move_done", self._real_move_done)
        for pseudo_axis in self.pseudos:
            event.disconnect(pseudo_axis, "sync_hard", self._pseudo_sync_hard)

        for real_axis in self.reals:
            event.disconnect(real_axis, "internal_position", self._real_position_update)
            event.disconnect(
                real_axis, "internal__set_position", self._real_setpos_update
            )

        self._reals_group = None
        self.reals = []
        self.pseudos = []

    def initialize_axis(self, axis):
        pass  # nothing to do

    def _add_axis(self, axis):
        self.pseudos.append(axis)
        event.connect(axis, "sync_hard", self._pseudo_sync_hard)

    def _pseudo_sync_hard(self):
        for real_axis in self.reals:
            real_axis.sync_hard()

    def _axis_tag(self, axis):
        return [
            tag
            for tag, axes in self._tagged.items()
            if tag != "real" and len(axes) == 1 and axis in axes
        ][0]

    def _get_set_positions(self):
        setpos_dict = dict()
        for axis in self.pseudos:
            setpos_dict[self._axis_tag(axis)] = axis.user2dial(axis._set_position)
        return setpos_dict

    def _real_position_update(self, pos, sender=None):
        with self._lock:
            # avoid recursion
            if self._in_real_pos_update:
                return

            for axis in self.pseudos:
                self._initialize_axis(axis)

            try:
                self._in_real_pos_update = True
                return self._calc_from_real()
            finally:
                self._in_real_pos_update = False

    def _real_setpos_update(self, _):
        real_setpos = dict()
        for axis in self.reals:
            real_setpos[self._axis_tag(axis)] = axis._set_position

        new_setpos = self.calc_from_real(real_setpos)

        for tagged_axis_name, setpos in new_setpos.items():
            axis = self._tagged[tagged_axis_name][0]
            axis.settings.set("_set_position", axis.dial2user(setpos))

    def _check_limits(self, axis, positions):
        self.check_limits(axis, positions)

    def check_limits(self, *axis_positions):
        if len(axis_positions) == 1:
            # assuming axis_positions is just a grouper object with axis, positions
            grouped_axis_positions = list(axis_positions[0])
        else:
            # backward compatibility
            grouped_axis_positions = list(grouped(axis_positions, 2))
        axes = set()
        positions_len = []
        for axis, pos in grouped_axis_positions:
            axes.add(axis)
            try:
                iter(pos)
            except TypeError:
                positions_len.append(1)
            else:
                positions_len.append(len(pos))
        try:
            left_axis = axes - set(self.pseudos)
            assert not left_axis
        except AssertionError:
            raise RuntimeError(f"Axes {left_axis} are not managed in this controller")

        # number of positions must be equals
        try:
            assert min(positions_len) == max(positions_len)
        except AssertionError:
            raise RuntimeError(
                f"Axes {axes} doesn't have the same number of positions to check"
            )

        axis_to_positions = self._get_complementary_pseudos_pos_dict(axes)

        position_len = positions_len[0]
        if position_len > 1:
            # need to extend other
            axis_to_positions = {
                tag: numpy.ones(position_len) * pos
                for tag, pos in axis_to_positions.items()
            }
        axis_to_positions.update(
            {self._axis_tag(axis): pos for axis, pos in grouped_axis_positions}
        )
        real_positions = self.calc_to_real(axis_to_positions)
        real_min_max = dict()
        for rtag, pos in real_positions.items():
            try:
                iter(pos)
            except TypeError:
                real_min_max[self._tagged[rtag][0]] = [pos]
            else:
                real_min_max[self._tagged[rtag][0]] = min(pos), max(pos)
        for real_axis, positions in real_min_max.items():
            for pos in set(positions):
                try:
                    real_axis.controller._check_limits(real_axis, pos)
                except ValueError as e:
                    message = e.args[0]
                    new_message = f"{', '.join([axis.name for axis in axes])} move to {positions} error:\n{message}"
                    raise ValueError(new_message)

    def _get_complementary_pseudos_pos_dict(self, axes):
        """ Find the other pseudos which are not in 'axes' and get their actual position.
            This complementary axes are necessary to compute the reals positions
            via the 'calc_to_real' method. 

            Args: 
                axes: list of Axis objects
            Return: {axis_tag:dial_pos, ...}
        """

        return {
            self._axis_tag(axis): axis.user2dial(axis._set_position)
            for axis in self.pseudos
            if axis not in axes
        }

    def _do_calc_from_real(self):
        real_positions_by_axis = self._reals_group.position
        real_positions = dict(
            [
                (self._axis_tag(axis), pos)
                for axis, pos in real_positions_by_axis.items()
            ]
        )
        return self.calc_from_real(real_positions)

    def _calc_from_real(self, *args):
        new_positions = self._do_calc_from_real()

        for tagged_axis_name, dial_pos in new_positions.items():
            axis = self._tagged[tagged_axis_name][0]
            if axis in self.pseudos:
                user_pos = axis.dial2user(dial_pos)
                axis.settings.set("dial_position", dial_pos)
                axis.settings.set("position", user_pos)
            else:
                raise RuntimeError("Cannot assign position to real motor")
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

    def _get_motion_pos_dict(self, motion_list):
        """ get all necessary pseudos with their positions to compute calc_to_real"""
        return self._get_set_positions()

    def start_all(self, *motion_list):
        positions_dict = self._get_motion_pos_dict(motion_list)
        move_dict = dict()
        for tag, target_pos in self.calc_to_real(positions_dict).items():
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
        pos = axis.settings.get("dial_position")
        if pos is None:
            new_positions = self._calc_from_real()
            pos = new_positions[self._axis_tag(axis)]

        return pos

    def state(self, axis, new_state=None):
        return self._reals_group.state

    def set_position(self, axis, new_pos):
        if axis not in self.pseudos:
            raise RuntimeError(
                "Cannot set dial position on motor '%s` from CalcController" % axis.name
            )

        positions = self._get_set_positions()
        positions[self._axis_tag(axis)] = new_pos
        real_positions = self.calc_to_real(positions)
        for real_axis_tag, user_pos in real_positions.items():
            self._tagged[real_axis_tag][0].position = user_pos

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
            {self._axis_tag(caxis): caxis.position for caxis in self.pseudos}
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
            cpos = numpy.zeros(len(calc_positions), dtype=float)
            cpos[:] = caxis.position
            positions[self._axis_tag(caxis)] = cpos

        time = numpy.linspace(0.0, nb_points * time_per_point, nb_points)
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
                for axis, position in iter(final_real_axes_position.items())
            },
            spline_nb_points=spline_nb_points,
        )
        # check velocity and acceleration
        max_velocity = pt.max_velocity
        max_acceleration = pt.max_acceleration
        limits = pt.limits
        error_list = list()
        start_stop_acceleration = dict()
        for axis in final_real_axes_position:
            vel = axis.velocity
            acc = axis.acceleration
            axis_limits = axis.limits
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
                "Trajectory on calc axis **%s** cannot be done.\n" % calc_axis.name
            )
            error_message += "\n".join(error_list)
            raise ValueError(error_message)

        pvt = pt.pvt(acceleration_start_end=start_stop_acceleration)
        trajectories = [
            Trajectory(axis, pvt[axis.name]) for axis in final_real_axes_position
        ]

        return motor_group.TrajectoryGroup(*trajectories, calc_axis=calc_axis)

    def _check_trajectory(self, axis):
        if axis.controller.has_trajectory():
            return axis, []
        else:  # check if axis is part of calccontroller
            ctrl = axis.controller
            if isinstance(ctrl, CalcController):
                real_involved = ctrl.calc_to_real(
                    {ctrl._axis_tag(caxis): caxis.position for caxis in ctrl.pseudos}
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
                    cpos = numpy.zeros(len(axis_position), dtype=float)
                    cpos[:] = caxis.position
                    local_real_positions[ctrl._axis_tag(caxis)] = cpos

                dep_real_position = ctrl.calc_to_real(local_real_positions)
                ctrl._get_real_position(
                    dep_real_axes, dep_real_position, final_real_axes_position
                )

    def _is_already_on_position(self, axis, delta):
        """ With calculated axes, always return False to ensure it updates real axes that might 
            have been moved independently (i.e outside CalcMotor context). 
        """
        if axis not in self.reals:
            return False
        else:
            return super()._is_already_on_position(axis, delta)


def get_real_axes(*axes):
    """Return real axes from given axis objects"""
    real_axes_list = []
    for axis in axes:
        real_axes_list.append(axis)
        if isinstance(axis.controller, CalcController):
            real_axes_list += get_real_axes(*axis.controller.reals)
    return real_axes_list
