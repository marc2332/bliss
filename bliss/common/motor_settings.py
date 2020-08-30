# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import event
from bliss.common.greenlet_utils import KillMask
from bliss.config import settings, settings_cache
import collections
import sys


def setting_update_from_channel(value, setting_name=None, axis=None):
    # print('setting update from channel', axis.name, setting_name, str(value))
    if setting_name == "state":
        if "MOVING" in str(value):
            axis._set_moving_state(from_channel=True)
        else:
            if axis.is_moving:
                axis._set_move_done()

    try:
        event.send(axis, setting_name, value)
    except Exception:
        sys.excepthook(*sys.exc_info())


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
        self.convert_func = {}
        self.persistent_setting = {}
        self.config_setting = {}

        # 'offset' must be set BEFORE limits to ensure good dial/user conversion.
        self.add("offset", float)
        self.add("sign", int)
        self.add("backlash", float)
        self.add("velocity", float, config=True)
        self.add("jog_velocity", float)
        self.add("acceleration", float, config=True)
        self.add("low_limit", floatOrNone)
        self.add("high_limit", floatOrNone)
        self.add("dial_position", float)
        self.add("_set_position", float)
        self.add("position", float)
        self.add("state", stateSetting, persistent=False)
        self.add("steps_per_unit", float, config=True)

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


disabled_settings_namedtuple = collections.namedtuple(
    "disabled_settings", "names config_dict"
)


class AxisSettings:
    def __init__(self, axis):
        self.__axis = axis
        self.__state = None
        self._disabled_settings = disabled_settings_namedtuple(
            set(), dict(axis.config.config_dict)
        )
        cnx_cache = settings_cache.get_redis_client_cache()
        self._hash = settings.HashSetting(
            "axis.%s" % axis.name,
            default_values=axis.config.config_dict,
            connection=cnx_cache,
        )
        # Activate prefetch
        cnx_cache.add_prefetch(self._hash)

    def __iter__(self):
        for name in self.__axis.controller.axis_settings.setting_names:
            yield name

    def convert_func(self, setting_name):
        return self.__axis.controller.axis_settings.convert_func.get(setting_name)

    def config_settings(self):
        return self.__axis.controller.axis_settings.config_settings()

    def set(self, setting_name, value):
        if setting_name == "state":
            if self.__state == value:
                return
            self.__state = value
        """
        * set setting
        * send event
        * write
        """
        axis = self.__axis
        axis_settings = axis.controller.axis_settings
        if setting_name not in axis_settings.setting_names:
            raise ValueError(
                "No setting '%s` for axis '%s`" % (setting_name, axis.name)
            )
        convert_func = self.convert_func(setting_name)
        if convert_func is not None:
            value = convert_func(value)

        disabled_settings = self._disabled_settings
        if setting_name in disabled_settings.names:
            if (
                setting_name not in ("position", "dial_position")
                and axis_settings.persistent_setting[setting_name]
            ):
                disabled_settings.config_dict[setting_name] = value
        else:
            if axis_settings.persistent_setting[setting_name]:
                with KillMask():
                    axis.settings._hash[setting_name] = value

            axis._beacon_channels[setting_name].value = value

        event.send(axis, "internal_" + setting_name, value)
        try:
            event.send(axis, setting_name, value)
        except Exception:
            sys.excepthook(*sys.exc_info())

    def get(self, setting_name):
        axis = self.__axis
        axis_settings = axis.controller.axis_settings
        disabled_settings = self._disabled_settings

        if setting_name not in axis_settings.setting_names:
            raise ValueError(
                "No setting '%s` for axis '%s`" % (setting_name, axis.name)
            )

        if setting_name in disabled_settings.names:
            return disabled_settings.config_dict.get(setting_name)
        else:
            if axis_settings.persistent_setting[setting_name]:
                with KillMask():
                    value = axis.settings._hash.get(setting_name)
            else:
                chan = axis._beacon_channels.get(setting_name)
                if chan:
                    value = chan.value
                else:
                    value = None

            if value is not None:
                convert_func = self.convert_func(setting_name)
                if convert_func is not None:
                    value = convert_func(value)
            return value

    def clear(self, setting_name):
        axis = self.__axis
        axis_settings = axis.controller.axis_settings
        disabled_settings = self._disabled_settings

        if setting_name in disabled_settings.names:
            disabled_settings.config_dict[setting_name] = None
        else:
            axis.settings._hash[setting_name] = None
            # reset beacon channel, if it is there
            try:
                channel = axis._beacon_channels[setting_name]
            except KeyError:
                pass
            else:
                channel.value = channel.default_value

    def disable_cache(self, setting_name, flag=True):
        """
        Remove cache for specified setting
        """
        if setting_name == "position":
            self.disable_cache("dial_position", flag)

        self.clear(setting_name)

        if flag:
            self._disabled_settings.names.add(setting_name)
        else:
            try:
                self._disabled_settings.names.remove(setting_name)
            except KeyError:
                pass
