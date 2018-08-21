# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
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

    try:
        move_type = state.move_type
    except Exception:
        move_type = ""
    s = axis.AxisState(state)
    s.move_type = move_type
    return s


class ControllerAxisSettings:
    def __init__(self):
        self.setting_names = [
            "velocity",
            "position",
            "dial_position",
            "_set_position",
            "state",
            "offset",
            "acceleration",
            "low_limit",
            "high_limit",
        ]
        self.convert_funcs = {
            "velocity": float,
            "position": float,
            "dial_position": float,
            "_set_position": float,
            "state": stateSetting,
            "offset": float,
            "low_limit": floatOrNone,
            "high_limit": floatOrNone,
            "acceleration": float,
        }

    def add(self, setting_name, convert_func=str):
        if setting_name not in self.setting_names:
            self.setting_names.append(setting_name)
            self.convert_funcs[setting_name] = convert_func

    def get(self, axis, setting_name):
        if setting_name not in self.setting_names:
            raise ValueError(
                "No setting '%s` for axis '%s`" % (setting_name, axis.name)
            )
        if setting_name not in ("state", "position"):
            hash_setting = settings.HashSetting("axis.%s" % axis.name)
            value = hash_setting.get(setting_name)
        else:
            value = None
        if value is None:
            chan = axis._beacon_channels[setting_name]
            value = chan.value
        if value is not None:
            convert_func = self.convert_funcs.get(setting_name)
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
        convert_func = self.convert_funcs.get(setting_name)
        if convert_func is not None:
            value = convert_func(value)

        if setting_name not in ("state", "position"):
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

    def get(self, setting_name):
        return self.__axis.controller.axis_settings.get(self.__axis, setting_name)

    def __iter__(self):
        for name in self.__axis.controller.axis_settings.setting_names:
            yield name
