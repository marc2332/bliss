# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
General purpose motion hooks.
"""

import logging

from gevent import sleep

from bliss.common.hook import MotionHook


class SleepHook(MotionHook):
    """
    Wait a specified amount of time before and/or after motion.
    Useful when you cannot query the control system when a pre or post move
    condition has finished (ex: when using air-pads you cannot usualy query
    when the air-pad has finished inflating/deflating so you need to wait
    an arbitrary time after you ask it to inflate/deflate)

    Configuration example:

    .. code-block:: yaml

        name: ngy_airpad
        class: SleepHook
        module: motors.hooks
        pre_move_wait: 0.5    # optional (default: 0s)
        post_move_wait: 0.3   # optional (default: 0s)
    """

    def __init__(self, name, config):
        self._log = logging.getLogger("{0}({1})".format(self.__class__.__name__, name))
        self.debug = self._log.debug
        self.config = config
        self.name = name
        super(SleepHook, self).__init__()

    def wait(self, phase):
        t = float(self.config.get("{0}_wait".format(phase)))
        if t:
            self.debug("start %s wait (%ss)...", phase, t)
            sleep(t)
            self.debug("finished %s wait (%ss)", phase, t)

    def pre_move(self, motion_list):
        self.wait("pre_move")

    def post_move(self, motion_list):
        self.wait("post_move")


class WagoHook(MotionHook):
    """
    Wago generic value hook. Apply *pre_value* before moving and *post_value* after moving.

    Configuration example:

    .. code-block:: yaml

        name: ngy_airpad
        class: WagoHook
        module: motors.hooks
        wago: $wcid00a
        channel: ngy_air
        pre_move:
            value: 1
            wait: 1    # optional (default: 0s)
        post_move:
            value: 0
            wait: 1    # optional (default: 0s)
    """

    def __init__(self, name, config):
        self._log = logging.getLogger("{0}({1})".format(self.__class__.__name__, name))
        self.debug = self._log.debug
        self.config = config
        self.name = name
        self.wago = config["wago"]
        self.channel = config["channel"]
        super(WagoHook, self).__init__()

    def add_axis(self, axis):
        if len(self.axes):
            axis_name = list(self.axes.keys())[0]
            raise ValueError(
                "Cannot attach WagoAirpadHook {0!r} to {1!r}. "
                "It is already attached to {2!r}".format(
                    self.name, axis.name, axis_name
                )
            )
        super(WagoHook, self).add_axis(axis)

    def set(self, phase):
        value = self.config[phase]["value"]
        wait = self.config[phase].get("wait", 0)
        self.debug("start setting %s value to %s...", phase, value)
        self.wago.set(self.channel, value)
        self.debug("finished setting %s value to %s", phase, value)
        if wait:
            self.debug("start %s wait (%ss)...", phase, wait)
            sleep(wait)
            self.debug("finished %s wait (%ss)", phase, wait)

    def pre_move(self, motion_list):
        self.set("pre_move")

    def post_move(self, motion_list):
        self.set("post_move")


class AirpadHook(WagoHook):
    """
    Wago air-pad hook. Turn on air-pad before moving. Turn off air-pad after moving.

    Configuration example:

    .. code-block:: yaml

        name: ngy_airpad
        class: AirpadHook
        module: motors.hooks
        wago: $wcid00a
        channel: ngy_air
        pre_move:
            wait:  1         # optional (default: 0s)
        post_move:
            wait:  2         # optional (default: 0s)
    """

    def __init__(self, name, config):
        config.setdefault("pre_move")["value"] = 1
        config.setdefault("post_move")["value"] = 0
        super(AirpadHook, self).__init__(name, config)
