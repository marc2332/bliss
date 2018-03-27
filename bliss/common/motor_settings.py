# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import log as elog
from bliss.common import event
from bliss.config import settings
from bliss.config import channels
import functools

def setting_update_from_channel(value, setting_name=None, axis=None):
    #print 'setting update from channel', axis.name, setting_name, str(value)

    if not axis._hw_control:
        if setting_name == 'state':
            if 'MOVING' in str(value):
                axis._set_moving_state(from_channel=True)
            else:
                if axis.is_moving:
                    axis._set_move_done()

        event.send(axis, setting_name, value)


def get_from_config(axis, setting_name):
    try:
        return axis.config.get(setting_name)
    except KeyError:
        return


def get_axis_setting(axis, setting_name):
    hash_setting = settings.HashSetting("axis.%s" % axis.name)
    if len(hash_setting) == 0:
        # there is no setting value in cache
        setting_value = get_from_config(axis, setting_name)
        if setting_value is not None:
            # write setting to cache
            hash_setting[setting_name] = setting_value
    else:
        setting_value = hash_setting.get(setting_name)
        if setting_value is None:
            # take setting value from config
            setting_value = get_from_config(axis, setting_name)
            if setting_value is not None:
                # write setting to cache
                hash_setting[setting_name] = setting_value

    try:
        beacon_channels = axis._beacon_channels
    except AttributeError:
        beacon_channels = dict()
        axis._beacon_channels = beacon_channels

    try:
        chan = beacon_channels[setting_name]
    except KeyError:
        chan_name = "axis.%s.%s" % (axis.name, setting_name)
        cb = functools.partial(setting_update_from_channel, setting_name=setting_name, axis=axis)
        if setting_value is None:
            chan = channels.Channel(chan_name, callback=cb)
        else:
            chan = channels.Channel(chan_name, default_value=setting_value, callback=cb)
        chan._setting_update_cb = cb
        beacon_channels[setting_name] = chan
    else:
        if setting_value is None:
            setting_value = chan.value

    return setting_value


def floatOrNone(x):
    if x is not None:
        return float(x)

class ControllerAxisSettings:

    def __init__(self):
        self.setting_names = ["velocity", "position", "dial_position", "_set_position", "state",
                              "offset", "acceleration", "low_limit", "high_limit"]
        from bliss.common import axis
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "dial_position": float,
            "_set_position": float,
            "state": axis.AxisState,
            "offset": float,
            "low_limit": floatOrNone,
            "high_limit": floatOrNone,
            "acceleration": float}

    def add(self, setting_name, convert_func=str):
        self.setting_names.append(setting_name)
        self.convert_funcs[setting_name] = convert_func

    def load_from_config(self, axis):
        for setting_name in self.setting_names:
            try:
                setting_value = get_axis_setting(axis, setting_name)
            except RuntimeError:
                elog.debug("settings.py : no '%s' in settings." % setting_name)
                return
            if setting_value is None:
                elog.debug("settings.py : '%s' is None (not found?)." % setting_name)
                continue
            elog.debug("settings.py : '%s' is %r" % (setting_name, setting_value))

    def get(self, axis, setting_name):
        value = get_axis_setting(axis, setting_name)
        if value is not None:
            convert_func = self.convert_funcs.get(setting_name)
            if convert_func is not None:
                value = convert_func(value)
        return value

    def set(self, axis, setting_name, value):
        '''
        * set setting
        * send event
        * write
        '''
        convert_func = self.convert_funcs.get(setting_name)
        if convert_func is not None:
            value = convert_func(value)

        if setting_name not in ('state', 'position'):
            settings.HashSetting("axis.%s" % axis.name)[setting_name] = value
        axis._beacon_channels[setting_name].value = value
        event.send(axis, 'internal_'+setting_name, value)
        event.send(axis, setting_name, value)

class AxisSettings:

    def __init__(self, axis):
        self.__axis = axis

    def set(self, setting_name, value):
        return self.__axis.controller.axis_settings.set(
            self.__axis, setting_name, value)

    def get(self, setting_name):
        return self.__axis.controller.axis_settings.get(self.__axis, setting_name)

    def load_from_config(self):
        return self.__axis.controller.axis_settings.load_from_config(
            self.__axis)

    def __iter__(self):
        for name in self.__axis.controller.axis_settings.setting_names:
            yield name
