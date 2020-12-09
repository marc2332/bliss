# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import collections
import functools
import inspect
import math
import sys

from bliss.common import event
from bliss.common.greenlet_utils import KillMask
from bliss.config.channels import Channel
from bliss.config import settings
from bliss.config.conductor.client import get_caching_redis_proxy


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
        self.hardware_setting = {}

        # 'offset' must be set BEFORE limits to ensure good dial/user conversion.
        self.add("sign", int)
        self.add("offset", float)
        self.add("backlash", float)
        self.add("low_limit", floatOrNone)
        self.add("high_limit", floatOrNone)
        self.add("velocity", float, config=True, hardware=True)
        self.add("jog_velocity", float, hardware=True)
        self.add("acceleration", float, config=True, hardware=True)
        self.add("dial_position", float, hardware=True)
        self.add("_set_position", float)
        self.add("position", float, hardware=True)
        self.add("state", stateSetting, persistent=False, hardware=True)
        self.add("steps_per_unit", float, config=True)

    @property
    def config_settings(self):
        return tuple(
            setting for setting, config in self.config_setting.items() if config
        )

    def add(
        self,
        setting_name,
        convert_func=str,
        persistent=True,
        config=False,
        hardware=False,
    ):
        if setting_name not in self.setting_names:
            self.setting_names.append(setting_name)
            self.convert_func[setting_name] = convert_func
            self.persistent_setting[setting_name] = persistent
            self.config_setting[setting_name] = config
            self.hardware_setting[setting_name] = hardware


disabled_settings_namedtuple = collections.namedtuple(
    "disabled_settings", "names config_dict"
)


class AxisSettings:
    def __init__(self, axis):
        self.__axis = axis
        self.__prev_state = None
        self.__prev_position = None
        self.__prev_dial = None
        self._beacon_channels = {}
        self._disabled_settings = disabled_settings_namedtuple(
            set(), dict(axis.config.config_dict)
        )
        cnx_cache = get_caching_redis_proxy()
        self._hash = settings.HashSetting(
            "axis.%s" % axis.name,
            default_values=axis.config.config_dict,
            connection=cnx_cache,
        )
        # Activate prefetch
        cnx_cache.add_prefetch(self._hash)

    @property
    def setting_names(self):
        yield from self.__axis.controller.axis_settings.setting_names

    def convert_func(self, setting_name):
        return self.__axis.controller.axis_settings.convert_func.get(setting_name)

    @property
    def config_settings(self):
        return self.__axis.controller.axis_settings.config_settings

    @property
    def hardware_settings(self):
        return self.__axis.controller.axis_settings.hardware_settings

    def register_channels_callbacks(self):
        for chan in self._beacon_channels.values():
            chan.register_callback(chan._setting_update_cb)

    def unregister_channels_callbacks(self):
        for chan in self._beacon_channels.values():
            chan.unregister_callback(chan._setting_update_cb)

    def _create_channel(self, setting_name):
        chan_name = "axis.%s.%s" % (self.__axis.name, setting_name)
        chan = Channel(chan_name)
        cb = functools.partial(
            setting_update_from_channel, setting_name=setting_name, axis=self.__axis
        )
        chan._setting_update_cb = cb
        return chan

    def init_channels(self):
        self._beacon_channels.clear()
        for setting_name in self.__axis.controller.axis_settings.setting_names:
            self._beacon_channels[setting_name] = self._create_channel(setting_name)
        self.register_channels_callbacks()

    def _get_setting_or_config_value(self, name, default=None):
        # return setting or config parameter
        converter = self.convert_func(name)
        value = self.get(name)
        if value is None:
            value = self.__axis.config.get(name, converter, default=default)
        return value

    def check_config_settings(self):
        axis = self.__axis
        props = dict(
            inspect.getmembers(axis.__class__, lambda o: isinstance(o, property))
        )
        config_settings = []
        for setting_name in self.config_settings:
            # check if setting is in config
            value = axis.config.get(setting_name)
            if value is None:
                raise RuntimeError(
                    "Axis %s: missing configuration key '%s`"
                    % (axis.name, setting_name)
                )
            if setting_name == "steps_per_unit":
                # steps_per_unit is read-only
                continue
            config_settings.append(setting_name)
            # check if setting has a method to initialize (set) its value,
            # without actually executing the property
            try:
                assert callable(props[setting_name].fset)
            except AssertionError:
                raise RuntimeError(
                    "Axis %s: missing method '%s` to set setting value"
                    % (axis.name, setting_name)
                )
        return config_settings

    def init(self):
        """ Initialize settings

        "config settings" are those that **must** be in YML config like
        steps per unit, acceleration and velocity ; otherwise settings
        can optionally be present in the config file.
        Config settings must have a property setter on the Axis object.
        "persistent settings" are stored in redis, like position for example;
        in any case, when a setting is set its value is emitted via a
        dedicated channel.
        Some settings can be both config+persistent (like velocity) or
        none (like state, which is only emitted when it changes, but not stored
        at all)
        """
        axis = self.__axis

        config_settings = self.check_config_settings()
        config_steps_per_unit = axis.config.get("steps_per_unit", float)

        if axis.no_offset:
            sign = 1
            offset = 0
        else:
            sign = self._get_setting_or_config_value("sign", 1)
            offset = self._get_setting_or_config_value("offset", 0)
        self.set("sign", sign)
        self.set("offset", offset)

        self.set("backlash", self._get_setting_or_config_value("backlash", 0))

        low_limit_dial = self._get_setting_or_config_value("low_limit")
        high_limit_dial = self._get_setting_or_config_value("high_limit")

        if config_steps_per_unit:
            cval = config_steps_per_unit
            rval = self._hash.raw_get("steps_per_unit")
            # Record steps_per_unit
            if rval is None:
                self.set("steps_per_unit", cval)
            else:
                rval = float(rval)
                if cval != rval:
                    ratio = rval / cval
                    new_dial = axis.dial * ratio

                    self.set("steps_per_unit", cval)
                    if not axis.no_offset:
                        # calculate offset so user pos stays the same
                        self.set("offset", axis.position - axis.sign * new_dial)
                    self.set("dial_position", new_dial)

                    if math.copysign(rval, cval) != rval:
                        ll, hl = low_limit_dial, high_limit_dial
                        low_limit_dial, high_limit_dial = -hl, -ll

        self.set("low_limit", low_limit_dial)
        self.set("high_limit", high_limit_dial)

        for setting_name in config_settings:
            value = self._get_setting_or_config_value(setting_name)
            setattr(axis, setting_name, value)

    def set(self, setting_name, value):
        # the last 3 tests prevent recursion when getting one of those
        # settings, that can do a set in some circumstances (first time or
        # 'no settings axis' for example), that emit a new setting event,
        # that can execute a callback that can get state or position...
        if setting_name == "state":
            if self.__prev_state == value:
                return
            self.__prev_state = value
        if setting_name == "position":
            if self.__prev_position == value:
                return
            self.__prev_position = value
        if setting_name == "dial_position":
            if self.__prev_dial == value:
                return
            self.__prev_dial = value

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
                not axis_settings.hardware_setting[setting_name]
                and axis_settings.persistent_setting[setting_name]
            ):
                disabled_settings.config_dict[setting_name] = value
        else:
            if axis_settings.persistent_setting[setting_name]:
                with KillMask():
                    self._hash[setting_name] = value

            self._beacon_channels[setting_name].value = value

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
            raise NameError("No setting '%s` for axis '%s`" % (setting_name, axis.name))

        if setting_name in disabled_settings.names:
            if axis_settings.hardware_setting[setting_name]:
                return  # will force hardware read
            else:
                return disabled_settings.config_dict.get(setting_name)

        if axis_settings.persistent_setting[setting_name]:
            with KillMask():
                value = self._hash.get(setting_name)
        else:
            chan = self._beacon_channels.get(setting_name)
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
        disabled_settings = self._disabled_settings

        if setting_name in disabled_settings.names:
            disabled_settings.config_dict[setting_name] = None
        else:
            self._hash[setting_name] = None
            # reset beacon channel, if it is there
            try:
                channel = self._beacon_channels[setting_name]
            except KeyError:
                pass
            else:
                channel.close()
                self._beacon_channels[setting_name] = self._create_channel(setting_name)

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
