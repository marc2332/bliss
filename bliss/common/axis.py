# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Axis related classes (:class:`~bliss.common.axis.Axis`, \
:class:`~bliss.common.axis.AxisState` and :class:`~bliss.common.axis.Motion`)

These classes are part of the bliss motion subsystem.
They are not to be instantiated directly. They are the objects produced
as calls to :meth:`~bliss.config.static.Config.get`. Example::

    >>> from bliss.config.static import get_config

    >>> cfg = get_config()
    >>> energy = cfg.get('energy')
    >>> energy
    <bliss.common.axis.Axis object at 0x7f7baa7f6d10>

    >>> energy.move(120)
    >>> print(energy.position)
    120.0

    >>> print energy.state()
    READY (Axis is READY)
"""

from bliss.common import log as elog
from bliss.common.task_utils import *
from bliss.common.motor_config import StaticConfig
from bliss.common.motor_settings import AxisSettings
from bliss.common import event
from bliss.common.utils import Null
from bliss.config.static import get_config
from bliss.common.encoder import Encoder
import gevent
import re
import types
import functools

#: Default polling time
DEFAULT_POLLING_TIME = 0.02


def get_encoder(name):
  cfg = get_config()
  enc = cfg.get(name)
  if not isinstance(enc, Encoder):
    raise TypeError("%s is not an Encoder" % name)
  return enc


def get_axis(name):
  cfg = get_config()
  axis = cfg.get(name)
  if not isinstance(axis, Axis):
    raise TypeError("%s is not an Axis" % name)
  return axis


class Modulo(object):
    def __init__(self, mod=360):
        self.modulo = mod

    def __call__(self, axis):
        dial_pos = axis.dial()
        axis.dial(dial_pos % self.modulo)    	
        axis.position(dial_pos % self.modulo)


class Motion(object):
    """Motion information

    Represents a specific motion. The following members are present:

    * *axis* (:class:`Axis`): the axis to which this motion corresponds to
    * *target_pos* (:obj:`float`): final motion position
    * *delta* (:obj:`float`): motion displacement
    * *backlash* (:obj:`float`): motion backlash
    """

    def __init__(self, axis, target_pos, delta):
        self.__axis = axis
        self.target_pos = target_pos
        self.delta = delta
        self.backlash = 0

    @property
    def axis(self):
        """Reference to :class:`Axis`"""
        return self.__axis


class Axis(object):
    """
    Bliss motor axis

    Typical usage goes through the bliss configuration (see this module
    documentation above for an example)
    """

    def lazy_init(func):
        @functools.wraps(func)
        def func_wrapper(self, *args, **kwargs):
            self.controller._initialize_axis(self)
            return func(self, *args, **kwargs)
        return func_wrapper

    def __init__(self, name, controller, config):
        self.__name = name
        self.__controller = controller
        self.__config = StaticConfig(config)
        self.__settings = AxisSettings(self)
        self.__move_done = gevent.event.Event()
        self.__move_done.set()
        self.__custom_methods_list = list()
        self.__custom_attributes_dict = dict()
        self.__move_task = None
        self.__stopped = False
        self._in_group_move = False
        self.no_offset = False

    @property
    def name(self):
        """Axis name"""
        return self.__name

    @property
    def controller(self):
        """Reference to :class:`~bliss.controllers.motor.Controller`"""
        return self.__controller

    @property
    def config(self):
        """Reference to the :class:`~bliss.common.motor_config.StaticConfig`"""
        return self.__config

    @property
    def settings(self):
        """
        Reference to the
        :class:`~bliss.controllers.motor_settings.AxisSettings`
        """
        return self.__settings

    @property
    def is_moving(self):
        """
        Tells if the axis is moving (:obj:`bool`)
        """
        return not self.__move_done.is_set()

    @property
    def _hw_control(self):
        """Return whether axis is currently driving hardware"""
        if self._in_group_move:
            return True
        if self.__move_task is not None:
            return self.is_moving 
        return False

    @property
    def offset(self):
        """Current offset in user units (:obj:`float`)"""
        offset = self.settings.get("offset")
        if offset is None:
            offset = 0
            self.settings.set('offset', 0)
        return offset

    @property
    def backlash(self):
        """Current backlash in user units (:obj:`float`)"""
        return self.config.get("backlash", float, 0)

    @property
    def sign(self):
        """Current motor sign (:obj:`int`) [-1, 1]"""
        return self.config.get("sign", int, 1)

    @property
    def steps_per_unit(self):
        """Current steps per unit (:obj:`float`)"""
        return self.config.get("steps_per_unit", float, 1)

    @property
    def encoder_steps_per_unit(self):
        """Current encoder steps per unit (:obj:`float`)"""
        if self.encoder is not None:
            return self.encoder.steps_per_unit
        else:
            return self.config.get("encoder_steps_per_unit",float,
                                   self.steps_per_unit)
    @property
    def tolerance(self):
        """Current tolerance in dial units (:obj:`float`)"""
        return self.config.get("tolerance", float, 1E-4)

    @property
    def encoder(self):
        """
        Reference to :class:`~bliss.common.encoder.Encoder` or None if no
        encoder is defined
        """
        try:
            encoder_name = self.config.get("encoder")
        except KeyError:
            return None
        else:
            return get_encoder(encoder_name)

    @property
    def custom_methods_list(self):
        """
        List of custom methods defined for this axis.
        Internal usage only
        """
        # Returns a *copy* of the custom methods list.
        return self.__custom_methods_list[:]

    @property
    def custom_attributes_list(self):
        """
        List of custom attributes defined for this axis.
        Internal usage only
        """
        ad = self.__custom_attributes_dict

        # Converts dict into list...
        _attr_list = [(a_name, ad[a_name][0], ad[a_name][1]) for i, a_name in enumerate(ad)]

        # Returns a *copy* of the custom attributes list.
        return _attr_list[:]

    def set_setting(self, *args):
        """Sets the given settings"""
        self.settings.set(*args)

    def get_setting(self, *args):
        """Returns the values for the given settings"""
        return self.settings.get(*args)

    def has_tag(self, tag):
        """
        Tells if the axis has the given tag

        Args:
            tag (str): tag name

        Returns:
            bool: True if the axis has the tag or False otherwise
        """
        for t, axis_list in self.__controller._tagged.iteritems():
            if t != tag:
                continue
            if self.name in [axis.name for axis in axis_list]:
                return True
        return False

    def _add_custom_method(self, method, name, types_info=(None, None)):
        setattr(self, name, method)
        self.__custom_methods_list.append((name, types_info))

    @lazy_init
    def on(self):
        """Turns the axis on"""
        if self.is_moving:
            return

        self.__controller.set_on(self)
        state = self.__controller.state(self)
        self.settings.set("state", state)

    @lazy_init
    def off(self):
        """Turns the axis off"""
        if self.is_moving:
            raise RuntimeError("Can't set power off while axis is moving")

        self.__controller.set_off(self)
        state = self.__controller.state(self)
        self.settings.set("state", state)

    def reset(self):
        """Resets the axis (calls finalize + initialize on its controller)"""
        if self.is_moving:
            raise RuntimeError("Can't reset while axis is moving")
        self.__controller.finalize_axis(self)
        self.__controller._initialize_axis(self)

    @lazy_init
    def _set_position(self, new_set_pos=None):
        if new_set_pos is None:
            sp = self.settings.get("_set_position")
            if sp is not None:
                return sp
            new_set_pos = self.position()
        self.settings.set("_set_position", new_set_pos)
        return new_set_pos

    @lazy_init
    def measured_position(self):
        """
        Returns the encoder value in user units.

        Returns:
            float: encoder value in user units
        """
        return self.dial2user(self.dial_measured_position())

    @lazy_init
    def dial_measured_position(self):
        """
        Returns the dial encoder position.

        Returns:
            float: dial encoder position
        """
        return self.__controller.read_encoder(self.encoder) / self.encoder.steps_per_unit

    @lazy_init
    def dial(self, new_dial=None):
        """
        Returns current dial position, or set new dial if *new_dial* argument
        is provided

        Keyword Args:
            new_dial: new dial position [default: None, meaning just return \
            current dial]

        Returns:
            float: current dial position (dimensionless)
        """
        if new_dial is None:
            dial_pos = self.settings.get("dial_position")
            if dial_pos is None:
                dial_pos = self._read_dial_and_update() 
            return dial_pos

        if self.is_moving:
            raise RuntimeError("%s: can't set axis dial position " 
                               "while moving" % self.name)

        user_pos = self.position()

        try:
            # Send the new value in motor units to the controller
            # and read back the (atomically) reported position
            new_hw = new_dial * self.steps_per_unit
            hw_pos = self.__controller.set_position(self, new_hw)
            dial_pos = hw_pos / self.steps_per_unit
            self.settings.set("dial_position", dial_pos)
        except NotImplementedError:
            dial_pos = self._read_dial_and_update(update_user=False)

        # update user_pos or offset setting
        if self.no_offset:
            user_pos = dial_pos 
        self._set_position_and_offset(user_pos)
        return dial_pos

    @lazy_init
    def position(self, new_pos=None):
        """
        Returns current user position, or set new user position if *new_pos*
        argument is provided

        Keyword Args:
            new_pos: new user position (in user units) [default: None, \
            meaning just return current user position]

        Returns:
            float: current user position (user units)
        """
        elog.debug("axis.py : position(new_pos=%r)" % new_pos)
        if new_pos is None:
            pos = self.settings.get("position")
            if pos is None:
                pos = self.dial2user(self.dial())
            return pos

        if self.is_moving:
            raise RuntimeError("%s: can't set axis user position "
                               "while moving" % self.name)

        if self.no_offset:
            return self.dial(new_pos)
        else:
            return self._set_position_and_offset(new_pos)

    @lazy_init 
    def _read_dial_and_update(self, update_user=True, write=True):
        dial_pos = self._hw_position()
        self.settings.set("dial_position", dial_pos, write=write)
        if update_user:
            user_pos = self.dial2user(dial_pos, self.offset)
            self.settings.set("position", user_pos, write=write)
        return dial_pos

    @lazy_init
    def _hw_position(self):
        try:
            curr_pos = self.__controller.read_position(self) / self.steps_per_unit
        except NotImplementedError:
            # this controller does not have a 'position'
            # (e.g like some piezo controllers)
            curr_pos = 0
        return curr_pos

    def _calc_offset(self, new_pos, dial_pos):
        return new_pos - self.sign * dial_pos

    def _set_position_and_offset(self, new_pos):
        dial_pos = self.dial()
        prev_offset = self.offset
        self._set_position(new_pos)
        self.settings.set("offset", self._calc_offset(new_pos, dial_pos))
        # update limits
        ll, hl = self.limits()
        lim_delta = self.offset - prev_offset
        self.limits(ll + lim_delta if ll is not None else ll,
                    hl + lim_delta if hl is not None else hl)
        self.settings.set("position", new_pos, write=True)
        return new_pos

    @lazy_init
    def state(self, read_hw=False):
        """
        Returns the axis state

        Keyword Args:
            read_hw (bool): read from hardware [default: False]

        Returns:
            AxisState: axis state
        """
        if read_hw:
            state = None
        else:
            if self.is_moving:
                return AxisState("MOVING")
            state = self.settings.get('state')
        if state is None:
            # really read from hw
            state = self.__controller.state(self)
        return state

    @lazy_init
    def get_info(self):
        """Returns controller specific information about the axis"""
        return self.__controller.get_info(self)

    def sync_hard(self):
        """Forces an axis synchronization with the hardware"""
        self.settings.set("state", self.state(read_hw=True), write=True) 
        self._read_dial_and_update()
        self._set_position(self.position())
        event.send(self, "sync_hard")
        
    @lazy_init
    def velocity(self, new_velocity=None, from_config=False):
        """
        Returns the current velocity. If *new_velocity* is given it sets
        the new velocity on the controller.

        Keyword Args:
            new_velocity (float): new velocity (user units/second) [default: \
            None, meaning return the current velocity]
            from_config (bool): if reading velocity (new_velocity is None), \
            if True, returns the current static configuration velocity, \
            otherwise, False returns velocity from the motor axis \
            [default: False]
        Returns:
            float: current velocity (user units/second)
        """
        if from_config:
            return self.config.get("velocity", float)

        if new_velocity is not None:
            # Write -> Converts into motor units to change velocity of axis."
            self.__controller.set_velocity(
                self, new_velocity * abs(self.steps_per_unit))
            _user_vel = self.__controller.read_velocity(self) / abs(self.steps_per_unit)
            self.settings.set("velocity", _user_vel)
        else:
            # Read -> Returns velocity read from motor axis.
            _user_vel = self.settings.get('velocity')
            if _user_vel is None:
                _user_vel = self.__controller.read_velocity(self) / abs(self.steps_per_unit)

        return _user_vel

    @lazy_init
    def acceleration(self, new_acc=None, from_config=False):
        """
        <new_acc> is given in user_units/s2.
        """
        if from_config:
            return self.config.get("acceleration", float)

        if new_acc is not None:
            if self.is_moving:
                raise RuntimeError("Cannot set acceleration while axis '%s` is moving." % self.name)

            # Converts into motor units to change acceleration of axis.
            self.__controller.set_acceleration(self, new_acc * abs(self.steps_per_unit))
            _ctrl_acc = self.__controller.read_acceleration(self)
            _acceleration = _ctrl_acc / abs(self.steps_per_unit)
            self.settings.set("acceleration", _acceleration)
        else:
            _acceleration = self.settings.get('acceleration')
            if _acceleration is None:
                _ctrl_acc = self.__controller.read_acceleration(self)
                _acceleration = _ctrl_acc / abs(self.steps_per_unit)

        return _acceleration

    @lazy_init
    def acctime(self, new_acctime=None, from_config=False):
        """
        Returns the current acceleration time. If *new_acctime* is given it sets
        the new acceleration time on the controller.

        Keyword Args:
            new_acctime (float): new acceleration (second) [default: \
            None, meaning return the current acceleration time]
            from_config (bool): if reading acceleration time (new_acctime \
            is None), if True, returns the current static configuration
            acceleration time, otherwise, False returns acceleration time \
            from the motor axis [default: False]
        Returns:
            float: current acceleration time (second)
        """
        if from_config:
            return self.velocity(from_config=True) / self.acceleration(from_config=True)

        if new_acctime is not None:
            # Converts acctime into acceleration.
            acc = self.velocity() / new_acctime
            self.acceleration(acc)

        _acctime = self.velocity() / self.acceleration()

        return _acctime

    @lazy_init
    def limits(self, low_limit=Null(), high_limit=Null(), from_config=False):
        """
        Returns the current software user limits. If *low_limit* or *high_limit*
        is given it sets the new values.

        Keyword Args:
            low_limit (float): new low limit (user units) [default: \
            None, meaning return the current limits]
            high_limit (float): new high limit (user units) [default: \
            None, meaning return the current limits]
            from_config (bool): if limits are not given, if True, returns \
            the current static configuration limits, otherwise, False returns \
            current limits from settings [default: False]

        Returns:
            tuple<float, float>: axis software limits (user units)
        """
        if from_config:
            ll = self.config.get("low_limit", float, None)
            hl = self.config.get("high_limit", float, None)
            return map(self.dial2user, (ll, hl))
        if not isinstance(low_limit, Null):
            self.settings.set("low_limit", low_limit)
        if not isinstance(high_limit, Null):
            self.settings.set("high_limit", high_limit)
        return self.settings.get('low_limit'), self.settings.get('high_limit')

    def _update_settings(self, state=None):
        self.settings.set("state", state if state is not None else self.state(), write=self._hw_control) 
        self._read_dial_and_update(write=self._hw_control)
 
    def _backlash_move(self, backlash_start, backlash, polling_time):
        final_pos = backlash_start + backlash
        backlash_motion = Motion(self, final_pos, backlash)
        self.__controller.prepare_move(backlash_motion)
        self.__controller.start_one(backlash_motion)
        self._handle_move(backlash_motion, polling_time)

    def _handle_move(self, motion, polling_time):
        state = self._wait_move(polling_time)
        if state in ['LIMPOS', 'LIMNEG']:
            raise RuntimeError(str(state))

        # gevent-atomic
        stopped, self.__stopped = self.__stopped, False
        if stopped or motion.backlash:
            dial_pos = self._read_dial_and_update()
            user_pos = self.dial2user(dial_pos)

        if motion.backlash:
            # broadcast reached position before backlash correction
            backlash_start = motion.target_pos
            if stopped:
                self._set_position(user_pos + self.backlash)
                backlash_start = dial_pos * self.steps_per_unit
            # axis has moved to target pos - backlash (or shorter, if stopped);
            # now do the final motion (backlash) relative to current/theo. pos
            elog.debug("doing backlash (%g)" % motion.backlash)
            self._backlash_move(backlash_start, motion.backlash, polling_time)
        elif stopped:
            self._set_position(user_pos)
        elif self.encoder is not None:
            self._do_encoder_reading()

    def _jog_move(self, velocity, direction, polling_time):
        self._wait_move(polling_time)

        dial_pos = self._read_dial_and_update()
        user_pos = self.dial2user(dial_pos)

        if self.backlash:
            backlash = self.backlash / self.sign * self.steps_per_unit
            if cmp(direction, 0) != cmp(backlash, 0):
                self._set_position(user_pos + self.backlash)
                backlash_start = dial_pos * self.steps_per_unit
                self._backlash_move(backlash_start, backlash, polling_time)
        else:
            self._set_position(user_pos)

    def dial2user(self, position, offset=None):
        """
        Translates given position from dial units to user units

        Args:
            position (float): position in dial units

        Keyword Args:
            offset (float): alternative offset. None (default) means use current offset

        Returns:
            float: position in axis user units
        """
        if position is None:
            # see limits()
            return None
        if offset is None:
            offset = self.offset
        return (self.sign * position) + offset

    def user2dial(self, position):
        """
        Translates given position from user units to dial units

        Args:
            position (float): position in user units

        Returns:
            float: position in axis dial units
        """
        return (position - self.offset) / self.sign

    @lazy_init
    def prepare_move(self, user_target_pos, relative=False):
        """Prepare a motion. Internal usage only"""
        elog.debug("user_target_pos=%g, relative=%r" % (user_target_pos, relative))
        user_initial_dial_pos = self.dial()
        hw_pos = self._read_dial_and_update()

        elog.debug("hw_position=%g user_initial_dial_pos=%g" % (hw_pos, user_initial_dial_pos))

        if abs(user_initial_dial_pos - hw_pos) > self.tolerance:
            raise RuntimeError(
					"%s: discrepancy between dial (%f) and controller position (%f), aborting" % (
                     self.name, user_initial_dial_pos, hw_pos))

        if relative:
            user_initial_pos = self._set_position()
            user_target_pos += user_initial_pos
        else:
            user_initial_pos = self.dial2user(user_initial_dial_pos)

        dial_initial_pos = self.user2dial(user_initial_pos)
        dial_target_pos = self.user2dial(user_target_pos)
        self._set_position(user_target_pos)
        if abs(dial_target_pos - dial_initial_pos) < 1E-6:
            return

        elog.debug("prepare_move : user_initial_pos=%g user_target_pos=%g" %
                   (user_initial_pos, user_target_pos) +
                   "  dial_target_pos=%g dial_intial_pos=%g relative=%s" %
                   (dial_target_pos, dial_initial_pos, relative))

        # all positions are converted to controller units
        backlash = self.backlash / self.sign * self.steps_per_unit
        delta = (dial_target_pos - dial_initial_pos) * self.steps_per_unit
        target_pos = dial_target_pos * self.steps_per_unit

        if backlash:
            if cmp(delta, 0) != cmp(backlash, 0):
                # move and backlash are not in the same direction;
                # apply backlash correction, the move will happen
                # in 2 steps
                target_pos -= backlash
                delta -= backlash
            else:
                # don't do backlash correction
                backlash = 0

        # check software limits
        user_low_limit, user_high_limit = self.limits()
        if user_low_limit is not None:
            low_limit = self.user2dial(user_low_limit) * self.steps_per_unit
        else:
            low_limit = None
        if user_high_limit is not None:
            high_limit = self.user2dial(user_high_limit) * self.steps_per_unit
        else:
            high_limit = None
        if high_limit is not None and high_limit < low_limit:
            high_limit, low_limit = low_limit, high_limit
            user_high_limit, user_low_limit = user_low_limit, user_high_limit

        backlash_str = " (with %f backlash)" % self.backlash if backlash else ""
        if user_low_limit is not None:
            if target_pos < low_limit:
                raise ValueError(
                    "%s: move to `%f'%s would go below low limit (%f)" %
                    (self.name, user_target_pos, backlash_str, user_low_limit))
        if user_high_limit is not None:
            if target_pos > high_limit:
                raise ValueError(
                    "%s: move to `%f' %s would go beyond high limit (%f)" %
                    (self.name, user_target_pos, backlash_str, user_high_limit))

        motion = Motion(self, target_pos, delta)
        motion.backlash = backlash

        self.__controller.prepare_move(motion)

        return motion

    def _set_moving_state(self, from_channel=False):
        self.__stopped = False
        self.__move_done.clear()
        if from_channel:
            self.__move_task = None
        self.settings.set("state", AxisState("MOVING"), write=not from_channel)
        event.send(self, "move_done", False)

    def _set_move_done(self, move_task):
        if move_task is not None:
            if not move_task._being_waited:
                try:
                    move_task.get()
                except gevent.GreenletExit:
                    pass
                except:
                    sys.excepthook(*sys.exc_info())
        self.__move_done.set()
        event.send(self, "move_done", True)

    def _check_ready(self):
        initial_state = self.state()
        if initial_state != "READY":
            raise RuntimeError("axis %s state is \
                                %r" % (self.name, str(initial_state)))

    def _start_move_task(self, funct, *args, **kws):
        start_event = gevent.event.Event()
        @task
        def sync_funct(*args, **kws):
            start_event.wait()
            return funct(*args, **kws)
        kws = dict(kws)
        being_waited = kws.pop('being_waited', True)
        self.__move_task = sync_funct(*args, wait=False, **kws)
        self.__move_task._being_waited = being_waited
        self.__move_task.link(self._set_move_done)
        self._set_moving_state()
        start_event.set()

    @lazy_init
    def move(self, user_target_pos, wait=True, relative=False, polling_time=DEFAULT_POLLING_TIME):
        """
        Move axis to the given absolute/relative position

        Args:
            user_target_pos: destination (user units)
        Keyword Args:
            wait (bool): wait or not for end of motion
            relative (bool): False if *user_target_pos* is given in absolute \
            position or True if it is given in relative position
            polling_time (float): motion loop polling time (seconds)
        """
        elog.debug("user_target_pos=%g  wait=%r relative=%r" % (user_target_pos, wait, relative))
        if self.__controller.is_busy():
            raise RuntimeError("axis %s: controller is busy" % self.name)
        self._check_ready()

        motion = self.prepare_move(user_target_pos, relative)
        if motion is None:
            return

        with error_cleanup(self._cleanup_stop):
            self.__controller.start_one(motion)
        
        self._start_move_task(self._do_handle_move, motion, polling_time,
                              being_waited=wait)

        if wait:
            self.wait_move()

    @lazy_init
    def jog(self, velocity, reset_position=None, polling_time=DEFAULT_POLLING_TIME):
        """
        Start to move axis at constant velocity

        Args:
            velocity: signed velocity for constant speed motion
        """
        if self.__controller.is_busy():
            raise RuntimeError("axis %s: controller is busy" % self.name)
        self._check_ready()
       
        if velocity == 0:
            return

        saved_velocity = self.velocity()

        with error_cleanup(functools.partial(self._cleanup_stop, jog=True), 
                           functools.partial(self._jog_cleanup, saved_velocity, reset_position)):
            self.velocity(abs(velocity)) #change velocity, to have settings updated accordingly
            velocity_in_steps = velocity * self.steps_per_unit
            direction = 1 if velocity_in_steps > 0 else -1
            self.__controller.start_jog(self, abs(velocity_in_steps), direction)

        self._start_move_task(self._do_jog_move, saved_velocity, velocity, direction, reset_position, polling_time, being_waited=False)

    def _do_encoder_reading(self):
        enc_dial = self.encoder.read()
        curr_pos = self._read_dial_and_update()
        if abs(curr_pos - enc_dial) > self.encoder.tolerance:
            raise RuntimeError("'%s' didn't reach final position.(enc_dial=%g, curr_pos=%g)" %
                               (self.name, enc_dial, curr_pos))

    def _do_handle_move(self, motion, polling_time):
        with error_cleanup(self._cleanup_stop):
            self._handle_move(motion, polling_time)

    def _jog_cleanup(self, saved_velocity, reset_position):
        self.velocity(saved_velocity)

        if reset_position == 0:
            def reset_dial(_):
                self.dial(0)
                self.position(0)
            self.__move_task.link(reset_dial)
        elif callable(reset_position):
            def reset_pos(_):
                reset_position(self)
            self.__move_task.link(reset_pos)

    def _do_jog_move(self, saved_velocity, velocity, direction, reset_position, polling_time):
        with cleanup(functools.partial(self._jog_cleanup, saved_velocity, reset_position)):
            with error_cleanup(functools.partial(self._cleanup_stop, jog=True)):
                self._jog_move(velocity, direction, polling_time)

    def rmove(self, user_delta_pos, wait=True, polling_time=DEFAULT_POLLING_TIME):
        """
        Move axis to the given relative position.

        Same as :meth:`move` *(relative=True)*

        Args:
            user_delta_pos: motor displacement (user units)
        Keyword Args:
            wait (bool): wait or not for end of motion
            polling_time (float): motion loop polling time (seconds)
        """
        elog.debug("user_delta_pos=%g  wait=%r" % (user_delta_pos, wait))
        return self.move(user_delta_pos, wait, relative=True, polling_time=polling_time)

    def wait_move(self):
        """
        Wait for the axis to finish motion (blocks current :class:`Greenlet`)

        If axis is not moving returns immediately
        """
        if not self.is_moving:
            return
        if self.__move_task is None:
            # move has been started externally
            with error_cleanup(self.stop):
                self.__move_done.wait()
        else:
            self.__move_task._being_waited = True
            with error_cleanup(self.stop):
                self.__move_done.wait()
            try:
                self.__move_task.get()
            except gevent.GreenletExit:
                pass

    def _wait_move(self, polling_time=DEFAULT_POLLING_TIME, ctrl_state_funct='state'):
        while True:
            state_funct = getattr(self.__controller, ctrl_state_funct)
            state = state_funct(self)
            self._update_settings(state)
            if state != "MOVING":
                return state
            gevent.sleep(polling_time)
        
    def _cleanup_stop(self, jog=False):
        if jog:
            self.__controller.stop_jog(self)
        else:
            self.__controller.stop(self)
        self._wait_move()
        self.sync_hard()

    def _do_stop(self):
        self.__controller.stop(self)
        self._set_stopped()

    def _set_stopped(self):
        self.__stopped = True

    @lazy_init
    def stop(self, wait=True):
        """
        Stops the current motion

        If axis is not moving returns immediately

        Args:
            wait (bool): wait for the axis to decelerate before returning \
            [default: True]
        """
        if self.is_moving:
            self._do_stop()
            if wait:
                self.wait_move()

    @lazy_init
    def home(self, switch=1, wait=True):
        """
        Searches the home switch

        Args:
            wait (bool): wait for search to finish [default: True]
        """
        self._check_ready()

        self.__controller.home_search(self, switch)
        self._start_move_task(self._wait_home, switch, being_waited=wait)

        if wait:
            self.wait_move()

    def _wait_home(self, switch):
        with cleanup(self.sync_hard):
            with error_cleanup(self._cleanup_stop):
                self._wait_move(ctrl_state_funct='home_state')

    @lazy_init
    def hw_limit(self, limit, wait=True):
        """
        Go to a hardware limit

        Args:
            limit (int): positive means "positive limit"
            wait (bool): wait for axis to finish motion before returning \
            [default: True]
        """
        limit = int(limit)
        self._check_ready()

        self.__controller.limit_search(self, limit)
        self._start_move_task(self._wait_limit_search, limit, being_waited=wait)

        if wait:
            self.wait_move()

    def _wait_limit_search(self, limit):
        with cleanup(self.sync_hard):
            with error_cleanup(self._cleanup_stop):
                self._wait_move()

    def settings_to_config(self, velocity=True, acceleration=True, limits=True):
        """
        Saves settings (velo acc limits) into config (XML file or beacon YML).
        """
        if velocity:
            self.__config.set('velocity', self.velocity())
        if acceleration:
            self.__config.set('acceleration', self.acceleration())
        if limits:
            def limit2config(l):
                return self.user2dial(l) if l is not None else l
            ll, hl = map(limit2config, self.limits())
            self.__config.set('low_limit', ll)
            self.__config.set('high_limit', hl)
        if any((velocity, acceleration, limits)):
            self.__config.save()

    def apply_config(self, reload=True):
        """
        Applies configuration values to settings (ie: reset axis)
        """
        if reload:
            self.config.reload()
        # Applies velocity and acceleration only if possible.
        # Try to execute <config_name> function to check if axis supports it.
        for config_param in ['velocity', 'acceleration']:
            rw_function = getattr(self, config_param)
            try:
                rw_function(rw_function(from_config=True))
            except (NotImplementedError, KeyError):
                elog.debug("'%s' for '%s' is not implemented" % (config_param, self.name))
            else:
                elog.debug("set '%s' for '%s' done." % (config_param, self.name))

        self.limits(*self.limits(from_config=True))


class AxisRef(object):
    """Object representing a named reference to an :class:`Axis`."""

    def __init__(self, name, _, config):
        self.__name = name
        self.__config = config
        self.settings = AxisSettings(None)

    @property
    def name(self):
        """Axis reference name"""
        return self.__name

    @property
    def config(self):
        """Reference to the :class:`~bliss.common.motor_config.StaticConfig`"""
        return self.__config


class AxisState(object):
    """
    Standard states:
      MOVING : 'Axis is moving'
      READY  : 'Axis is ready to be moved (not moving ?)'
      FAULT  : 'Error from controller'
      LIMPOS : 'Hardware high limit active'
      LIMNEG : 'Hardware low limit active'
      HOME   : 'Home signal active'
      OFF    : 'Axis is disabled (must be enabled to move (not ready ?))'

    When creating a new instance, you can pass any number of arguments, each
    being either a string or tuple of strings (state, description). They
    represent custom axis states.
    """

    #: state regular expression validator
    STATE_VALIDATOR = re.compile("^[A-Z0-9]+\s*$")

    _STANDARD_STATES = {
        "READY" : "Axis is READY",
        "MOVING": "Axis is MOVING",
        "FAULT" : "Error from controller",
        "LIMPOS": "Hardware high limit active",
        "LIMNEG": "Hardware low limit active",
        "HOME"  : "Home signal active",
        "OFF"   : "Axis is disabled (must be enabled to move (not ready ?))"
    }

    @property
    def READY(self):
        """Axis is ready to be moved"""
        return "READY" in self._current_states

    @property
    def MOVING(self):
        """Axis is moving"""
        return "MOVING" in self._current_states

    @property
    def FAULT(self):
        """Error from controller"""
        return "FAULT" in self._current_states

    @property
    def LIMPOS(self):
        """Hardware high limit active"""
        return "LIMPOS" in self._current_states

    @property
    def LIMNEG(self):
        """Hardware low limit active"""
        return "LIMNEG" in self._current_states

    @property
    def OFF(self):
        """Axis is disabled (must be enabled to move (not ready ?))"""
        return "OFF" in self._current_states

    @property
    def HOME(self):
        """Home signal active"""
        return "HOME" in self._current_states

    def __init__(self, *states):
        """
        <*states> : can be one or many string or tuple of strings (state, description)
        """

        # set of active states.
        self._current_states = list()

        # dict of descriptions of states.
        self._state_desc = self._STANDARD_STATES

        for state in states:
            if isinstance(state, tuple):
                self.create_state(*state)
                self.set(state[0])
            else:
                if isinstance(state, AxisState):
                    state = state.current_states()
                self._set_state_from_string(state)

    def states_list(self):
        """
        Returns a list of available/created states for this axis.
        """
        return list(self._state_desc)

    def _check_state_name(self, state_name):
        if not isinstance(state_name, str) or not AxisState.STATE_VALIDATOR.match(state_name):
            raise ValueError(
                "Invalid state: a state must be a string containing only block letters")

    def _has_custom_states(self):
        return not self._state_desc is AxisState._STANDARD_STATES

    def create_state(self, state_name, state_desc=None):
        """
        Adds a new custom state

        Args:
            state_name (str): name of the new state
        Keyword Args:
            state_desc (str): state description [default: None]

        Raises:
            ValueError: if state_name is invalid
        """
        # Raises ValueError if state_name is invalid.
        self._check_state_name(state_name)
        if state_desc is not None and '|' in state_desc:
            raise ValueError("Invalid state: description contains invalid character '|'")

        # if it is the first time we are creating a new state, create a
        # private copy of standard states to be able to modify locally
        if not self._has_custom_states():
            self._state_desc = AxisState._STANDARD_STATES.copy()

        if state_name not in self._state_desc:
            # new description is put in dict.
            if state_desc is None:
                state_desc = "Axis is %s" % state_name
            self._state_desc[state_name] = state_desc

            # Makes state accessible via a class property.
            # NO: we can't, because the objects of this class will become unpickable,
            # as the class changes...
            # Error message is: "Can't pickle class XXX: it's not the same object as XXX"
            # add_property(self, state_name, lambda _: state_name in self._current_states)

    """
    Flags ON a given state.
    ??? what about other states : clear other states ???  -> MG : no
    ??? how to flag OFF ???-> no : on en cree un nouveau.
    """
    def set(self, state_name):
        """
        Activates the given state on this AxisState

        Args:
            state_name (str): name of the state to activate

        Raises:
            ValueError: if state_name is invalid
        """
        if state_name in self._state_desc:
            if state_name not in self._current_states:
                self._current_states.append(state_name)

                # Mutual exclusion of READY and MOVING
                if state_name == "READY":
                    if self.MOVING:
                        self._current_states.remove("MOVING")
                if state_name == "MOVING":
                    if self.READY:
                        self._current_states.remove("READY")
        else:
            raise ValueError("state %s does not exist" % state_name)

    def clear(self):
        """Clears all current states"""
        # Flags all states off.
        self._current_states = list()

    def current_states(self):
        """
        Returns a string of current states.

        Returns:
            str: *|* separated string of current states or string *UNKNOWN* \
            if there is no current state
        """
        states = [
            "%s%s" % (state.rstrip(), " (%s)" % self._state_desc[state] if self._state_desc.get(state) else "")
            for state in map(str, list(self._current_states))]

        if len(states) == 0:
            return "UNKNOWN"

        return " | ".join(states)

    def _set_state_from_string(self, state):
        # is state_name a full list of states returned by self.current_states() ?
        # (copy constructor)
        if '(' in state:
            full_states = [s.strip() for s in state.split('|')]
            p = re.compile('^([A-Z0-9]+)\s\((.+)\)$')
            for full_state in full_states:
                m = p.match(full_state)
                state = m.group(1)
                desc = m.group(2)
                self.create_state(state, desc)
                self.set(state)
        else:
            if state != 'UNKNOWN':
                self.create_state(state)
                self.set(state)

    def __str__(self):
        return self.current_states()

    def __eq__(self, other):
        if isinstance(other, AxisState):
            other = str(other)
        if isinstance(other, str):
            state = self.current_states()
            return other in state
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def new(self, share_states=True):
        """
        Create a new AxisState which contains the same possible states but no
        current state.

        If this AxisState contains custom states and *share_states* is True
        (default), the possible states are shared with the new AxisState.
        Otherwise, a copy of possible states is created for the new AxisState.

        Keyword Args:
            share_states: If this AxisState contains custom states and
                          *share_states* is True (default), the possible states
                          are shared with the new AxisState. Otherwise, a copy
                          of possible states is created for the new AxisState.

        Returns:
            AxisState: a copy of this AxisState with no current states
        """
        result = AxisState()
        if self._has_custom_states() and not share_states:
            result._state_desc = self._state_desc.copy()
        else:
            result._state_desc = self._state_desc
        return result
