# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.motor_config import StaticConfig
from bliss.common.motor_settings import ControllerAxisSettings
from bliss.common.axis import Axis, AxisRef
from bliss.common.motor_group import Group
from bliss.common import event
from bliss.common.utils import set_custom_members
from bliss.config.channels import Cache
from gevent import lock

# make the link between encoder and axis, if axis uses an encoder
# (only 1 encoder per axis of course)
ENCODER_AXIS = dict()


class Controller(object):
    '''
    Motor controller base class

    See Also:
        :ref:`bliss-how-to-motor-controller`
    '''

    def __init__(self, name, config, axes, encoders, shutters, switches):
        self.__name = name
        self.__config = StaticConfig(config)
        self.__initialized_axis = dict()
        self.__initialized_hw = Cache(self, "initialized", default_value = False)
        self.__lock = lock.Semaphore()
        self.__initialized_hw_axis = dict()
        self._axes = dict()
        self._encoders = dict()
        self._shutters = dict()
        self._switches = dict()
        self.__initialized_encoder = dict()
        self._tagged = dict()

        self.axis_settings = ControllerAxisSettings()

        for encoder_name, encoder_class, encoder_config in encoders:
            encoder = encoder_class(encoder_name, self, encoder_config)
            self._encoders[encoder_name] = encoder
            self.__initialized_encoder[encoder] = False

        for axis_name, axis_class, axis_config in axes:
            axis = axis_class(axis_name, self, axis_config)
            self._axes[axis_name] = axis
            axis_tags = axis_config.get('tags')
            if axis_tags:
                for tag in axis_tags.split():
                    self._tagged.setdefault(tag, []).append(axis)

            # For custom attributes and commands.
            # NB : AxisRef has no controller.
            if not isinstance(axis, AxisRef):
                set_custom_members(self, axis, axis.controller._initialize_axis)

            ##
            self.__initialized_axis[axis] = False
            self.__initialized_hw_axis[axis] = Cache(axis, "initialized", default_value = False)
            if axis_config.get("encoder"):
                encoder_name = axis_config.get("encoder")
                ENCODER_AXIS[encoder_name] = axis_name

        for obj_config_list,object_dict in ((shutters,self._shutters),
                                            (switches,self._switches)):
            for obj_name, obj_class, obj_config in obj_config_list:
                if obj_class is None:
                    raise ValueError("You have to specify a **class** for object named: %s" % obj_name)
                object_dict[obj_name] = obj_class(obj_name, self, obj_config)
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
    def switchs(self):
        return self._switches

    def get_switch(self, name):
        return self._switches[name]

    @property
    def name(self):
        return self.__name

    @property
    def config(self):
        return self.__config

    def _update_refs(self, config):
        for tag, axis_list in self._tagged.iteritems():
            for i, axis in enumerate(axis_list):
                if not isinstance(axis, AxisRef):
                    continue
                referenced_axis = config.get(axis.name)
                if not isinstance(referenced_axis, Axis):
                    raise TypeError("%s: invalid axis '%s`, not an Axis" % (self.name, axis.name))
                self.axes[axis.name] = referenced_axis
                axis_list[i] = referenced_axis

    def initialize(self):
        pass

    def initialize_hardware(self):
        """
        This method should contain all commands needed to initialize the controller hardware.
        i.e: reset, power on....
    	This initialization will be called once (by the first client).
        """
        pass

#    def __del__(self):
#        self.finalize()

    def finalize(self):
        pass

    def _initialize_axis(self, axis, *args, **kwargs):
        if self.__initialized_axis[axis]:
            return

        with self.__lock:
            if not self.__initialized_hw.value:
                self.initialize_hardware()
                self.__initialized_hw.value = True
            
        axis.settings.load_from_config()

        self.initialize_axis(axis)
        self.__initialized_axis[axis] = True

        if not self.__initialized_hw_axis[axis].value:

            # apply settings or config parameters
            def get_setting_or_config_value(name, converter=float):
                value = axis.settings.get(name)
                if value is None:
                    try:
                        value = axis.config.get(name, converter)
                    except:
                        return None
                return value

            mandatory_config_list = list()

            for config_param in ['velocity', 'acceleration']:
                # Try to see if controller supports setting the <config_param> by
                # checking if it oveloads default set_<config_name> method
                set_name = "set_%s" % config_param
                base_set_method = getattr(Controller, set_name)
                set_method = getattr(axis.controller.__class__, set_name)
                if base_set_method != set_method:
                    mandatory_config_list.append(config_param)

            for setting_name in mandatory_config_list:
                value = get_setting_or_config_value(setting_name)
                if value is None:
                    raise RuntimeError("%s is missing in configuration for axis '%s`." % (setting_name, axis.name))
                meth = getattr(axis, setting_name)
                meth(value)

            low_limit = get_setting_or_config_value("low_limit")
            high_limit = get_setting_or_config_value("high_limit")
            axis.limits(low_limit, high_limit)

            self.initialize_hardware_axis(axis)
            self.__initialized_hw_axis[axis].value = True

    def get_axis(self, axis_name):
        axis = self._axes[axis_name]

        return axis

    def initialize_axis(self, axis):
        raise NotImplementedError

    def initialize_hardware_axis(self, axis):
        """
        This method should contain all commands needed to initialize the hardware for this axis.
        i.e: velocity, close loop configuration...
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

    def _initialize_encoder(self, encoder):
        if self.__initialized_encoder[encoder]:
            return
       
        if ENCODER_AXIS.get(encoder.name):
            axis_name = ENCODER_AXIS[encoder.name]
            axis = self.get_axis(axis_name)
            axis.controller._initialize_axis(axis)
 
        self.initialize_encoder(encoder)
        self.__initialized_encoder[encoder] = True

    def initialize_encoder(self, encoder):
        raise NotImplementedError

    def prepare_move(self, motion):
        return

    def start_jog(self, velocity, direction):
        raise NotImplementedError

    def start_one(self, motion):
        raise NotImplementedError

    def start_all(self, *motion_list):
        raise NotImplementedError

    def stop(self, axis):
        raise NotImplementedError

    def stop_jog(self, axis):
        return self.stop(axis)
 
    def stop_all(self, *motions):
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

        self._reals_group = None
        self.reals = []
        self.pseudos = []

    def initialize(self):
        for real_axis in self._tagged['real']:
            # check if real axis is really from another controller
            if real_axis.controller == self:
                raise RuntimeError(
                    "Real axis '%s` doesn't exist" % real_axis.name)
            self.reals.append(real_axis)
            real_axis.controller._initialize_axis(real_axis)

        self.pseudos = [axis for axis_name, axis in self.axes.iteritems()
                        if axis not in self.reals]
        
        self._reals_group = Group(*self.reals)
        event.connect(self._reals_group, 'move_done', self._real_move_done)

        calc = False
        for pseudo_axis in self.pseudos:
	    self._Controller__initialized_hw_axis[pseudo_axis].value = True
            self._initialize_axis(pseudo_axis)
	    event.connect(pseudo_axis, 'sync_hard', self._pseudo_sync_hard)
            if self.read_position(pseudo_axis) is None:
                # the pseudo axis position has *never* been calculated
                calc = True                        

        for real_axis in self.reals:
            event.connect(real_axis, 'internal_position', self._calc_from_real)
            event.connect(real_axis, 'internal__set_position', self._real_setpos_update)

        if calc:
	    self._calc_from_real()

    def initialize_axis(self, axis):
	pass

    def _pseudo_sync_hard(self):
        for real_axis in self.reals:
            real_axis.sync_hard()

    def _axis_tag(self, axis):
        return [tag for tag, axes in self._tagged.iteritems()
                if tag != 'real' and len(axes) == 1 and axis in axes][0]

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

    def _do_calc_from_real(self):
        real_positions_by_axis = self._reals_group.position()
        real_positions = dict([(self._axis_tag(axis), pos)
                               for axis, pos in real_positions_by_axis.items()])
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
        if st == 'READY':
            self._calc_from_real()
        return st
     
    def set_position(self, axis, new_pos):
        if not axis in self.pseudos:
            raise RuntimeError("Cannot set dial position on motor '%s` from CalcController" % axis.name)

        positions = self._get_set_positions()
        positions[self._axis_tag(axis)] = new_pos
        real_positions = self.calc_to_real(positions)
        for real_axis_tag, user_pos in real_positions.iteritems():
            self._tagged[real_axis_tag][0].position(user_pos)

        new_positions = self._calc_from_real()

        return new_positions[self._axis_tag(axis)]

