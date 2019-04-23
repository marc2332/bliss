# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import log as elog
from bliss.common import event
from bliss.config import settings


def setting_update_from_channel(value, setting_name=None, axis=None):
    # print 'setting update from channel', axis.name, setting_name, str(value)
    if setting_name == "state":
        if "MOVING" in str(value):
            axis._set_moving_state(from_channel=True)
        else:
            if axis.is_moving:
                axis._set_move_done()

    event.send(axis, setting_name, value)


def floatOrNone(x):
    if x is not None:
        return float(x)


def stateSetting(state):
    from bliss.common import axis

    s = axis.AxisState(state)
    return s


class ControllerAxisSettings:
    def __init__(self):
        self.setting_names = []
        self.disabled_settings = {}
        self.convert_func = {}
        self.persistent_setting = {}
        self.config_setting = {}

        self.add("velocity", float, config=True)
        self.add("acceleration", float, config=True)
        self.add("low_limit", floatOrNone)
        self.add("high_limit", floatOrNone)
        self.add("dial_position", float)
        self.add("offset", float)
        self.add("_set_position", float)
        self.add("position", float)
        self.add("state", stateSetting, persistent=False)
        self.add("steps_per_unit", float, persistent=True, config=True)

    def config_settings(self):
        return tuple(
            [setting for setting, config in self.config_setting.items() if config]
        )

    def add(self, setting_name, convert_func=str, persistent=True, config=False):
        if setting_name not in self.setting_names:
            self.setting_names.append(setting_name)
            self.convert_func[setting_name] = convert_func
            self.persistent_setting[setting_name] = persistent
            self.config_setting[setting_name] = config

    def get(self, axis, setting_name):
        if setting_name not in self.setting_names:
            raise ValueError(
                "No setting '%s` for axis '%s`" % (setting_name, axis.name)
            )

        disabled_settings = self.disabled_settings.get(axis, set())
        if setting_name in disabled_settings:
            return None

        if self.persistent_setting[setting_name]:
            hash_setting = settings.HashSetting("axis.%s" % axis.name)
            value = hash_setting.get(setting_name)
        else:
            value = None
        if value is None:
            chan = axis._beacon_channels.get(setting_name)
            if chan:
                value = chan.value
        if value is not None:
            convert_func = self.convert_func.get(setting_name)
            if convert_func is not None:
                value = convert_func(value)
        return value

    def set(self, axis, setting_name, value):
        """
        * set setting
        * send event
        * write
        """
        if setting_name not in self.setting_names:
            raise ValueError(
                "No setting '%s` for axis '%s`" % (setting_name, axis.name)
            )
        convert_func = self.convert_func.get(setting_name)
        if convert_func is not None:
            value = convert_func(value)

        if self.persistent_setting[setting_name]:
            settings.HashSetting("axis.%s" % axis.name)[setting_name] = value

        axis._beacon_channels[setting_name].value = value
        event.send(axis, "internal_" + setting_name, value)
        event.send(axis, setting_name, value)


class AxisSettings:
    def __init__(self, axis):
        self.__axis = axis
        self.__state = None

    def set(self, setting_name, value):
        if setting_name == "state":
            if self.__state == value:
                return
            self.__state = value
        return self.__axis.controller.axis_settings.set(
            self.__axis, setting_name, value
        )

    def convert_func(self, setting_name):
        return self.__axis.controller.axis_settings.convert_func[setting_name]

    def config_settings(self):
        return self.__axis.controller.axis_settings.config_settings()

    def get(self, setting_name):
        return self.__axis.controller.axis_settings.get(self.__axis, setting_name)

    def disable_cache(self, setting_name, flag=True):
        """
        Remove the cache setting for the a setting_name.
        """
        disabled_settings = self.__axis.controller.axis_settings.disabled_settings.setdefault(
            self.__axis, set()
        )
        if flag:
            disabled_settings.add(setting_name)
        else:
            try:
                disabled_settings.remove(setting_name)
            except KeyError:
                pass

    def __iter__(self):
        for name in self.__axis.controller.axis_settings.setting_names:
            yield name
