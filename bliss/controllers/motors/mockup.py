# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import math
import time
import random
import gevent

from bliss.controllers.motor import Controller
from bliss.common import log as elog
from bliss.common.axis import Axis, AxisState, MotionEstimation
from bliss.common import event

from bliss.common.hook import MotionHook
from bliss.common.utils import object_method
from bliss.common.utils import object_attribute_get, object_attribute_set

"""
mockup.py : a mockup controller for bliss.
To be used as skeleton to write bliss plugin controller.
"""

"""
config :
 'velocity' in unit/s
 'acceleration' in unit/s^2
 'steps_per_unit' in unit^-1  (default 1)
 'backlash' in unit
"""

class Trajectory(object):
    """
    Trajectory representation for a motion

    v|  pa,ta_________pb,tb
     |      //        \\
     |_____//__________\\_______> t
       pi,ti             pf,tf
           <--duration-->
    """
    def __init__(self, pi, pf, velocity, acceleration, ti=None):
        if ti is None:
            ti = time.time()
        self.ti = ti
        self.pi = pi = float(pi)
        self.pf = pf = float(pf)
        self.velocity = velocity = float(velocity)
        self.acceleration = acceleration = float(acceleration)
        self.p = pf - pi
        self.dp = abs(self.p)
        self.positive = pf > pi

        full_accel_time = velocity / acceleration
        full_accel_dp = 0.5 * acceleration * full_accel_time**2

        full_dp_non_const_vel = 2 * full_accel_dp
        self.reaches_top_vel = self.dp > full_dp_non_const_vel
        if self.reaches_top_vel:
            self.top_vel_dp = self.dp - full_dp_non_const_vel
            self.top_vel_time = self.top_vel_dp / velocity
            self.accel_dp = full_accel_dp
            self.accel_time = full_accel_time
            self.duration = self.top_vel_time + 2 * self.accel_time
            self.ta = self.ti + self.accel_time
            self.tb = self.ta + self.top_vel_time
            if self.positive:
                self.pa = pi + self.accel_dp
                self.pb = self.pa + self.top_vel_dp
            else:
                self.pa = pi - self.accel_dp
                self.pb = self.pa - self.top_vel_dp
        else:
            self.top_vel_dp = 0
            self.top_vel_time = 0
            self.accel_dp = self.dp / 2
            self.accel_time = math.sqrt(2 * self.accel_dp / acceleration)
            self.duration = 2 * self.accel_time
            self.velocity = acceleration * self.accel_time
            self.ta = self.tb = self.ti + self.accel_time
            if self.positive:
                pa_pb = pi + self.accel_dp
            else:
                pa_pb = pi - self.accel_dp
            self.pa = self.pb = pa_pb
        self.tf = self.ti + self.duration

    def position(self, instant=None):
        """Position at a given instant in time"""
        if instant is None:
            instant = time.time()
        if instant < self.ti:
            raise ValueError('instant cannot be less than start time')
        if instant > self.tf:
            return self.pf
        dt = instant - self.ti
        p = self.pi
        f = 1 if self.positive else -1
        if instant < self.ta:
            accel_dp = 0.5 * self.acceleration * dt**2
            return p + f * accel_dp

        p += f * self.accel_dp

        # went through the initial acceleration
        if instant < self.tb:
            t_at_max = dt - self.accel_time
            dp_at_max = self.velocity * t_at_max
            return p + f * dp_at_max
        else:
            dp_at_max = self.top_vel_dp
            decel_time = instant - self.tb
            decel_dp = 0.5 * self.acceleration * decel_time**2
            return p + f * dp_at_max + f * decel_dp

    def instant(self, position):
        """Instant when the trajectory passes at the given position"""
        d = position - self.pi
        dp = abs(d)
        if dp > self.dp:
           raise ValueError('position outside trajectory')

        dt = self.ti
        if dp > self.accel_dp:
            dt += self.accel_time
        else:
            return math.sqrt(2 * dp / self.acceleration) + dt

        top_vel_dp = dp - self.accel_dp
        if top_vel_dp > self.top_vel_dp:
            # starts deceleration
            dt += self.top_vel_time
            decel_dp = abs(position- self.pb)
            dt += math.sqrt(2 * decel_dp / self.acceleration)
        else:
            dt += top_vel_dp / self.velocity
        return dt

    def __repr__(self):
        return '{0}({1.pi}, {1.pf}, {1.velocity}, {1.acceleration}, {1.ti})' \
               .format(type(self).__name__, self)


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
        self.trajectory = Trajectory(pi, pf, velocity, acceleration, ti)


class Mockup(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self._axis_moves = {}
        self.__encoders = {}

        # Custom attributes.
        self.__voltages = {}
        self.__cust_attr_float = {}

        self.__error_mode = False
        self._hw_state = AxisState("READY")
        self.__hw_limit = float('-inf'), float('+inf')

        self._hw_state.create_state("PARKED", "mot au parking")

        # Access to the config.
        try:
            self.host = self.config.get("host")
        except:
            elog.debug("no 'host' defined in config for %s" % self.name)

        # Adds Mockup-specific settings.
        self.axis_settings.add('init_count', int)
        self.axis_settings.add('hw_position', float)

    """
    Controller initialization actions.
    """
    def initialize(self):
        # hardware initialization
        for axis_name, axis in self.axes.iteritems():
            axis.settings.set('init_count', 0)

    """
    Axes initialization actions.
    """
    def initialize_axis(self, axis):
        # this is to protect position reading,
        # indeed the mockup controller uses redis to store
        # a 'hardware position', and it is not allowed
        # to read a position before it has been written
        def set_pos(move_done, axis=axis):
            if move_done:
                self.set_position(axis, axis.dial()*axis.steps_per_unit)

        self._axis_moves[axis] = {
            "motion": None,
            "move_done_cb": set_pos }

        if axis.settings.get('hw_position') is None:
            axis.settings.set('hw_position', 0)

        event.connect(axis, "move_done", set_pos)

        self.__voltages[axis] = axis.config.get("default_voltage",
                                                int, default=220)
        self.__cust_attr_float[axis] = axis.config.get("default_cust_attr",
                                                       float, default=3.14)

        # this is to test axis are initialized only once
        axis.settings.set('init_count', axis.settings.get('init_count') + 1)

        if axis.encoder:
            self.__encoders.setdefault(axis.encoder, {})["axis"] = axis

    def initialize_encoder(self, encoder):
        self.__encoders.setdefault(encoder, {})["measured_noise"] = None
        self.__encoders[encoder]["steps"] = None

    """
    Actions to perform at controller closing.
    """
    def finalize(self):
        pass

    def _get_axis_motion(self, axis, t=None):
        """Get an updated motion object.
           Also updates the motor hardware position setting if a motion is
           occuring"""
        motion = self._axis_moves[axis]['motion']
        if motion:
            if t is None:
                t = time.time()
            pos = motion.trajectory.position(t)
            axis.settings.set('hw_position', pos)
            if t > motion.trajectory.tf:
                self._axis_moves[axis]['motion'] = motion = None
        return motion

    def set_hw_limits(self, axis, low_limit, high_limit):
        if low_limit is None:
            if axis.steps_per_unit > 0:
                low_limit = float('-inf')
            else:
                low_limit = float('+inf')
        if high_limit is None:
            if axis.steps_per_unit > 0:
                high_limit = float('+inf')
            else:
                high_limit = float('-inf')
        ll= axis.user2dial(low_limit)*axis.steps_per_unit
        hl = axis.user2dial(high_limit)*axis.steps_per_unit
        if hl < ll:
            raise ValueError('Cannot set hard low limit > high limit')
        self.__hw_limit = (ll, hl)

    def start_all(self, *motion_list):
        if self.__error_mode:
            raise RuntimeError("Cannot start because error mode is set")
        t0 = time.time()
        for motion in motion_list:
            self.start_one(motion, t0=t0)

    def start_one(self, motion, t0=None):
        if self.__error_mode:
            raise RuntimeError("Cannot start because error mode is set")
        axis = motion.axis
        if t0 is None:
            t0 = time.time()
        if self._get_axis_motion(axis):
            raise RuntimeError('Cannot start motion. Motion already in place')
        pos = self.read_position(axis)
        vel = self.read_velocity(axis)
        accel = self.read_acceleration(axis)
        end_pos = motion.target_pos
        axis_motion = Motion(pos, end_pos, vel, accel, self.__hw_limit, ti=t0)
        self._axis_moves[axis]['motion'] = axis_motion

    def start_jog(self, axis, velocity, direction):
        t0 = time.time()
        pos = self.read_position(axis)
        self.set_velocity(axis, velocity)
        accel = self.read_acceleration(axis)
        target = float('+inf') if direction > 0 else float('-inf')
        motion = Motion(pos, target, velocity, accel, self.__hw_limit, ti=t0)
        self._axis_moves[axis]['motion'] = motion

    def read_position(self, axis, t=None):
        """
        Returns the position (measured or desired) taken from controller
        in controller unit (steps).
        """
        gevent.sleep(0.005) #simulate I/O

        t = t or time.time()
        motion = self._get_axis_motion(axis, t)
        if motion is None:
            pos = axis.settings.get('hw_position')
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
            axis = self.__encoders[encoder]["axis"]

            _pos = self.read_position(axis) / float(axis.steps_per_unit)

            if self.__encoders[encoder]["measured_noise"] > 0:
                # Simulates noisy encoder.
                amplitude = self.__encoders[encoder]["measured_noise"]
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
        return axis.settings.get('velocity')*abs(axis.steps_per_unit)

    def set_velocity(self, axis, new_velocity):
        """
        <new_velocity> is in motor units
        """
        vel = new_velocity/abs(axis.steps_per_unit)
        axis.settings.set('velocity', vel)
        return vel

    """
    ACCELERATION
    """
    def read_acceleration(self, axis):
        """
        must return acceleration in controller units / s2
        """
        return axis.settings.get('acceleration')*abs(axis.steps_per_unit)

    def set_acceleration(self, axis, new_acceleration):
        """
        <new_acceleration> is in controller units / s2
        """
        acc = new_acceleration/abs(axis.steps_per_unit)
        axis.settings.set('acceleration', acc)
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
        if self._hw_state == "OFF":
            return AxisState("OFF")
        else:
            s = AxisState(self._hw_state)
            s.set("READY")
            return s

    """
    STATE
    """
    def state(self, axis):
        gevent.sleep(0.005) #simulate I/O
        motion = self._get_axis_motion(axis)
        if motion is None:
           return self._check_hw_limits(axis)
        else:
           return AxisState("MOVING")

    """
    Must send a command to the controller to abort the motion of given axis.
    """
    def stop(self, axis, t=None):
        motion = self._get_axis_motion(axis, t)
        if motion:
            self._axis_moves[axis]['motion'] = None

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

#    def home_set_hardware_position(self, axis, home_pos):
#        raise NotImplementedError

    def home_state(self, axis):
        if(time.time() - self._axis_moves[axis]["home_search_start_time"]) > 1:
            axis.settings.set("hw_position", 0)
            return AxisState("READY")
        else:
            return AxisState("MOVING")

    def limit_search(self, axis, limit):
        target = float('+inf') if limit > 0 else float('-inf')
        pos = self.read_position(axis)
        vel = self.read_velocity(axis)
        accel = self.read_acceleration(axis)
        motion = Motion(pos, target, vel, accel, self.__hw_limit)
        self._axis_moves[axis]['motion'] = motion

    def get_info(self, axis):
        return "turlututu chapo pointu : %s" % (axis.name)

    def get_id(self, axis):
        return "MOCKUP AXIS %s" % (axis.name)

    def set_position(self, axis, pos):
        motion = self._get_axis_motion(axis)
        if motion:
            raise RuntimeError("Cannot set position while moving !")

        axis.settings.set('hw_position', pos)
        self._axis_moves[axis]['target'] = pos
        self._axis_moves[axis]["end_t"] = None

        return pos

    def put_discrepancy(self, axis, disc):
        self.set_position(axis, self.read_position(axis)+disc)

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
    @object_method(name= "CustomGetTwice", types_info=("int", "int"))
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
    def _set_closed_loop(self, axis, onoff = True):
        pass #print "I set the closed loop ", onoff

    # Types by default (None, None)
    @object_method
    def custom_command_no_types(self, axis):
        print "print with no types"

    @object_method
    def generate_error(self, axis):
        # For testing purposes.
        raise RuntimeError("Testing Error")

    def custom_get_measured_noise(self, axis):
        noise = 0.0
        if not axis.encoder in self.__encoders:
            raise KeyError("cannot read measured noise: %s "
                           "doesn't have encoder" % axis.name)
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
        self.__encoders[axis.encoder]["axis"] = axis

    def set_error(self, error_mode):
        self.__error_mode = error_mode

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

class MockupAxis(Axis):

    def __init__(self, *args, **kwargs):
        Axis.__init__(self, *args, **kwargs)

    def prepare_move(self, *args, **kwargs):
        self.backlash_move = 0
        return Axis.prepare_move(self, *args, **kwargs)

    def _handle_move(self, motion, polling_time):
        self.target_pos = motion.target_pos
        self.backlash_move = motion.target_pos / \
            self.steps_per_unit if motion.backlash else 0
        return Axis._handle_move(self, motion, polling_time)


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
        if self.config.get('pre_move_error', False):
            raise self.Error('cannot pre_move')
        self.nb_pre_move += 1
        self.last_pre_move_args = motion_list

    def post_move(self, motion_list):
        if self.config.get('post_move_error', False):
            raise self.Error('cannot post_move')
        self.nb_post_move += 1
        self.last_post_move_args = motion_list
