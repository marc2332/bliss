# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import random
import gevent

from bliss.physics.trajectory import LinearTrajectory
from bliss.controllers.motor import Controller, ENCODER_AXIS
from bliss.common import log as elog
from bliss.common.axis import Axis, AxisState, get_axis
from bliss.common import event

from bliss.common.hook import MotionHook
from bliss.common.utils import object_method
from bliss.common.utils import object_attribute_get, object_attribute_set

"""
mockup.py : a mockup controller for bliss.

config :
 'velocity' in unit/s
 'acceleration' in unit/s^2
 'steps_per_unit' in unit^-1  (default 1)
 'backlash' in unit
"""


class Motion(object):
    """Describe a single motion"""

    def __init__(self, pi, pf, velocity, acceleration, hard_limits, ti=None):

        # TODO: take hard limits into account (complicated).
        # For now just shorten the movement
        self.hard_limits = low_limit, high_limit = hard_limits
        if pf > high_limit:
            pf = high_limit
        if pf < low_limit:
            pf = low_limit
        self.trajectory = LinearTrajectory(pi, pf, velocity, acceleration, ti)


class Mockup(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._axis_moves = {}
        self.__encoders = {}

        # Custom attributes.
        self.__voltages = {}
        self.__cust_attr_float = {}

        self._hw_state = AxisState("READY")
        self.__hw_limit = float("-inf"), float("+inf")

        self._hw_state.create_state("PARKED", "mot au parking")

        # Access to the config.
        try:
            self.host = self.config.get("host")
        except:
            elog.debug("no 'host' defined in config for %s" % self.name)

        # Adds Mockup-specific settings.
        self.axis_settings.add("init_count", int)
        self.axis_settings.add("hw_position", float)

    def read_hw_position(self, axis):
        return axis.settings.get("hw_position")

    def set_hw_position(self, axis, position):
        axis.settings.set("hw_position", position)

    """
    Controller initialization actions.
    """

    def initialize(self):
        for axis_name, axis in self.axes.items():
            axis.settings.set("init_count", 0)

    """
    Axes initialization actions.
    """

    def initialize_axis(self, axis):
        self._axis_moves[axis] = {"motion": None}

        if self.read_hw_position(axis) is None:
            self.set_hw_position(axis, 0)

        self.__voltages[axis] = axis.config.get("default_voltage", int, default=220)
        self.__cust_attr_float[axis] = axis.config.get(
            "default_cust_attr", float, default=3.14
        )

        # this is to test axis are initialized only once
        axis.settings.set("init_count", axis.settings.get("init_count") + 1)
        axis.stop_jog_called = False

    def initialize_encoder(self, encoder):
        self.__encoders.setdefault(encoder, {})["measured_noise"] = None
        self.__encoders[encoder]["steps"] = None
        axis_name = ENCODER_AXIS[encoder.name]
        self.__encoders[encoder]["axis"] = axis_name
        axis = get_axis(axis_name)
        if not axis in self._axis_moves:
            self.initialize_axis(axis)

    """
    Actions to perform at controller closing.
    """

    def finalize(self):
        pass

    def _get_axis_motion(self, axis, t=None):
        """Get an updated motion object.
           Also updates the motor hardware position setting if a motion is
           occuring"""
        motion = self._axis_moves[axis]["motion"]

        if motion:
            if t is None:
                t = time.time()
            pos = motion.trajectory.position(t)
            self.set_hw_position(axis, pos)
            if t > motion.trajectory.tf:
                self._axis_moves[axis]["motion"] = motion = None
        return motion

    def set_hw_limits(self, axis, low_limit, high_limit):
        if low_limit is None:
            low_limit = float("-inf")
        if high_limit is None:
            high_limit = float("+inf")
        if high_limit < low_limit:
            raise ValueError("Cannot set hard low limit > high limit")
        ll = axis.user2dial(low_limit) * axis.steps_per_unit
        hl = axis.user2dial(high_limit) * axis.steps_per_unit
        # low limit and high limits may now be exchanged,
        # because of the signs or steps per unit or user<->dial conversion
        if hl < ll:
            ll, hl = hl, ll
        self.__hw_limit = (ll, hl)

    def start_all(self, *motion_list):
        t0 = time.time()
        for motion in motion_list:
            self.start_one(motion, t0=t0)

    def start_one(self, motion, t0=None):
        axis = motion.axis
        if self._get_axis_motion(axis):
            raise RuntimeError("Cannot start motion. Motion already in place")
        pos = self.read_position(axis)
        vel = self.read_velocity(axis)
        accel = self.read_acceleration(axis)
        end_pos = motion.target_pos
        if t0 is None:
            t0 = time.time()
        axis_motion = Motion(pos, end_pos, vel, accel, self.__hw_limit, ti=t0)
        self._axis_moves[axis]["motion"] = axis_motion

    def start_jog(self, axis, velocity, direction):
        axis.stop_jog_called = False
        t0 = time.time()
        pos = self.read_position(axis)
        self.set_velocity(axis, velocity)
        accel = self.read_acceleration(axis)
        target = float("+inf") if direction > 0 else float("-inf")
        motion = Motion(pos, target, velocity, accel, self.__hw_limit, ti=t0)
        self._axis_moves[axis]["motion"] = motion

    def read_position(self, axis, t=None):
        """
        Returns the position (measured or desired) taken from controller
        in controller unit (steps).
        """
        gevent.sleep(0.005)  # simulate I/O

        t = t or time.time()
        motion = self._get_axis_motion(axis, t)
        if motion is None:
            pos = self.read_hw_position(axis)
        else:
            pos = motion.trajectory.position(t)
        return int(round(pos))

    def read_encoder(self, encoder):
        """
        returns encoder position.
        unit : 'encoder steps'
        """
        if self.__encoders[encoder]["steps"] is not None:
            enc_steps = self.__encoders[encoder]["steps"]
        else:
            axis_name = self.__encoders[encoder]["axis"]
            axis = get_axis(axis_name)

            _pos = self.read_position(axis) / float(axis.steps_per_unit)

            amplitude = self.__encoders[encoder]["measured_noise"]
            if amplitude is not None and amplitude > 0:
                # Simulates noisy encoder.
                noise_mm = random.uniform(-amplitude, amplitude)

                _pos += noise_mm

                enc_steps = _pos * encoder.steps_per_unit
            else:
                # "Perfect" encoder
                enc_steps = _pos * encoder.steps_per_unit

        self.__encoders[encoder]["steps"] = None

        return enc_steps

    def set_encoder(self, encoder, encoder_steps):
        self.__encoders[encoder]["steps"] = encoder_steps

    """
    VELOCITY
    """

    def read_velocity(self, axis):
        """
        Returns the current velocity taken from controller
        in motor units.
        """
        return axis.settings.get("velocity") * abs(axis.steps_per_unit)

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units
        """
        vel = new_velocity / abs(axis.steps_per_unit)
        axis.settings.set("velocity", vel)
        return vel

    """
    ACCELERATION
    """

    def read_acceleration(self, axis):
        """
        must return acceleration in controller units / s2
        """
        return axis.settings.get("acceleration") * abs(axis.steps_per_unit)

    def set_acceleration(self, axis, new_acceleration):
        """
        <new_acceleration> is in controller units / s2
        """
        acc = new_acceleration / abs(axis.steps_per_unit)
        axis.settings.set("acceleration", acc)
        return acc

    """
    ON / OFF
    """

    def set_on(self, axis):
        self._hw_state.clear()
        self._hw_state.set("READY")

    def set_off(self, axis):
        self._hw_state.set("OFF")

    """
    Hard limits
    """

    def _check_hw_limits(self, axis):
        ll, hl = self.__hw_limit
        pos = self.read_position(axis)
        if pos <= ll:
            return AxisState("READY", "LIMNEG")
        elif pos >= hl:
            return AxisState("READY", "LIMPOS")
        if self._hw_state.OFF:
            return AxisState("OFF")
        else:
            s = AxisState(self._hw_state)
            s.set("READY")
            return s

    """
    STATE
    """

    def state(self, axis):
        gevent.sleep(0.005)  # simulate I/O
        motion = self._get_axis_motion(axis)
        if motion is None:
            return self._check_hw_limits(axis)
        else:
            return AxisState("MOVING")

    def stop_jog(self, axis):
        axis.stop_jog_called = True
        return Controller.stop_jog(self, axis)

    """
    Must send a command to the controller to abort the motion of given axis.
    """

    def stop(self, axis, t=None):
        motion = self._get_axis_motion(axis, t)
        if motion:
            self._axis_moves[axis]["motion"] = None

    def stop_all(self, *motion_list):
        t = time.time()
        for motion in motion_list:
            self.stop(motion.axis, t=t)

    """
    HOME and limits search
    """

    def home_search(self, axis, switch):
        self._axis_moves[axis]["delta"] = switch
        self._axis_moves[axis]["end_t"] = None
        self._axis_moves[axis]["t0"] = time.time()
        self._axis_moves[axis]["home_search_start_time"] = time.time()

    def home_state(self, axis):
        if (time.time() - self._axis_moves[axis]["home_search_start_time"]) > 1:
            self.set_hw_position(axis, 0)
            return AxisState("READY")
        else:
            return AxisState("MOVING")

    def limit_search(self, axis, limit):
        target = float("+inf") if limit > 0 else float("-inf")
        pos = self.read_position(axis)
        vel = self.read_velocity(axis)
        accel = self.read_acceleration(axis)
        motion = Motion(pos, target, vel, accel, self.__hw_limit)
        self._axis_moves[axis]["motion"] = motion

    def get_info(self, axis):
        return "turlututu chapo pointu : %s" % (axis.name)

    def get_id(self, axis):
        return "MOCKUP AXIS %s" % (axis.name)

    def set_position(self, axis, pos):
        motion = self._get_axis_motion(axis)
        if motion:
            raise RuntimeError("Cannot set position while moving !")

        self.set_hw_position(axis, pos)
        self._axis_moves[axis]["target"] = pos
        self._axis_moves[axis]["end_t"] = None

        return pos

    def put_discrepancy(self, axis, disc):
        self.set_position(axis, self.read_position(axis) + disc)

    """
    Custom axis methods
    """
    # VOID VOID
    @object_method
    def custom_park(self, axis):
        elog.debug("custom_park : parking")
        self._hw_state.set("PARKED")

    # VOID LONG
    @object_method(types_info=("None", "int"))
    def custom_get_forty_two(self, axis):
        return 42

    # LONG LONG  + renaming.
    @object_method(name="CustomGetTwice", types_info=("int", "int"))
    def custom_get_twice(self, axis, LongValue):
        return LongValue * 2

    # STRING STRING
    @object_method(types_info=("str", "str"))
    def custom_get_chapi(self, axis, value):
        if value == "chapi":
            return "chapo"
        elif value == "titi":
            return "toto"
        else:
            return "bla"

    # STRING VOID
    @object_method(types_info=("str", "None"))
    def custom_send_command(self, axis, value):
        elog.debug("custom_send_command(axis=%s value=%r):" % (axis.name, value))

    # BOOL NONE
    @object_method(name="Set_Closed_Loop", types_info=("bool", "None"))
    def _set_closed_loop(self, axis, onoff=True):
        pass  # print "I set the closed loop ", onoff

    # Types by default (None, None)
    @object_method
    def custom_command_no_types(self, axis):
        print("print with no types")

    @object_method
    def generate_error(self, axis):
        # For testing purposes.
        raise RuntimeError("Testing Error")

    def custom_get_measured_noise(self, axis):
        noise = 0.0
        if not axis.encoder in self.__encoders:
            raise KeyError(
                "cannot read measured noise: %s " "doesn't have encoder" % axis.name
            )
        noise = self.__encoders[axis.encoder].get("measured_noise", None)

    @object_method(types_info=("float", "None"))
    def custom_set_measured_noise(self, axis, noise):
        """
        Custom axis method to add a random noise, given in user units,
        to measured positions. Set noise value to 0 to have a measured
        position equal to target position.
        By the way we add a ref to the coresponding axis.
        """
        self.__encoders[axis.encoder]["measured_noise"] = noise
        self.__encoders[axis.encoder]["axis"] = axis.name

    """
    Custom attributes methods
    """

    @object_attribute_get(type_info="int")
    def get_voltage(self, axis):
        return self.__voltages.setdefault(axis, 10000)

    @object_attribute_set(type_info="int")
    def set_voltage(self, axis, voltage):
        self.__voltages[axis] = voltage

    @object_attribute_get(type_info="float")
    def get_cust_attr_float(self, axis):
        return self.__cust_attr_float.setdefault(axis, 9.999)

    @object_attribute_set(type_info="float")
    def set_cust_attr_float(self, axis, value):
        self.__cust_attr_float[axis] = value

    def has_trajectory(self):
        return True

    def prepare_trajectory(self, *trajectories):
        pass

    def move_to_trajectory(self, *trajectories):
        pass

    def start_trajectory(self, *trajectories):
        pass

    def stop_trajectory(self, *trajectories):
        pass


class MockupAxis(Axis):
    def __init__(self, *args, **kwargs):
        Axis.__init__(self, *args, **kwargs)

    def prepare_move(self, *args, **kwargs):
        motion = Axis.prepare_move(self, *args, **kwargs)
        if motion is None:
            self.backlash_move = 0
            self.target_pos = None
        else:
            self.target_pos = motion.target_pos
            self.backlash_move = (
                motion.target_pos / self.steps_per_unit if motion.backlash else 0
            )
        return motion


class MockupHook(MotionHook):
    """Motion hook used for pytest"""

    class Error(Exception):
        """Mockup hook error"""

        pass

    def __init__(self, name, config):
        super(MockupHook, self).__init__()
        self.name = name
        self.config = config
        self.nb_pre_move = 0
        self.nb_post_move = 0
        self.last_pre_move_args = ()
        self.last_post_move_args = ()

    def pre_move(self, motion_list):
        if self.config.get("pre_move_error", False):
            raise self.Error("cannot pre_move")
        self.nb_pre_move += 1
        self.last_pre_move_args = motion_list

    def post_move(self, motion_list):
        if self.config.get("post_move_error", False):
            raise self.Error("cannot post_move")
        self.nb_post_move += 1
        self.last_post_move_args = motion_list


class FaultyMockup(Mockup):
    def __init__(self, *args, **kwargs):
        Mockup.__init__(self, *args, **kwargs)

        self.bad_state = False
        self.bad_start = False
        self.bad_state_after_start = False
        self.bad_stop = False
        self.bad_position = False
        self.state_recovery_delay = 1
        self.state_msg_index = 0

    def state(self, axis):
        if self.bad_state:
            self.state_msg_index += 1
            raise RuntimeError("BAD STATE %d" % self.state_msg_index)
        else:
            return Mockup.state(self, axis)

    def start_one(self, motion, **kw):
        self.state_msg_index = 0
        if self.bad_start:
            raise RuntimeError("BAD START")
        else:
            try:
                return Mockup.start_one(self, motion, **kw)
            finally:
                if self.bad_state_after_start:
                    self.bad_state = True
                    gevent.spawn_later(
                        self.state_recovery_delay, setattr, self, "bad_state", False
                    )

    def stop(self, axis, **kw):
        if self.bad_stop:
            raise RuntimeError("BAD STOP")
        else:
            return Mockup.stop(self, axis, **kw)

    def read_position(self, axis, t=None):
        if self.bad_position:
            raise RuntimeError("BAD POSITION")
        else:
            return Mockup.read_position(self, axis, t)


class CustomMockup(Mockup):
    def __init__(self, *args, **kwargs):
        Mockup.__init__(self, *args, **kwargs)

        self.axis_settings.add("custom_setting1", str)

    @object_method(types_info=(None, str))
    def set_custom_setting1(self, axis, new_value=None):
        pass

    def read_custom_setting1(self, axis):
        pass
