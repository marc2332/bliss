# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
General purpose motion hooks.
"""

from gevent import sleep

from bliss.common.hook import MotionHook
from bliss.common.logtools import *


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
        self.config = config
        self.name = name
        super(SleepHook, self).__init__()

    def wait(self, phase):
        t = float(self.config.get("{0}_wait".format(phase)))
        if t:
            log_debug(self, f"start {phase} wait ({t})...")
            sleep(t)
            log_debug(self, f"finished {phase} wait ({t})...")

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
        self.config = config
        self.name = name
        self.wago = config["wago"]
        self.channel = config["channel"]
        super(WagoHook, self).__init__()

    def _add_axis(self, axis):
        if len(self.axes):
            axis_name = list(self.axes.keys())[0]
            raise ValueError(
                "Cannot attach WagoAirpadHook {0!r} to {1!r}. "
                "It is already attached to {2!r}".format(
                    self.name, axis.name, axis_name
                )
            )
        super(WagoHook, self)._add_axis(axis)

    def set(self, phase):
        value = self.config[phase]["value"]
        wait = self.config[phase].get("wait", 0)
        log_debug(self, f"start setting {phase} value to {value}...")
        self.wago.set(self.channel, value)
        log_debug(self, f"finished setting {phase} value to {value}...")
        if wait:
            log_debug(self, f"start {phase} wait ({wait})...")
            sleep(wait)
            log_debug(self, f"finished {phase} wait ({wait})...")

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


class WagoAirHook(WagoHook):
    """
    Wago air hook. Turn on air (pad/brake/...) before moving. Turn off air (pad/brake/...) 
    after moving.
     - Optionally a channel_in can be added to get an hardware check like pressostat 
      device which tells if air is really on or off.
     - Optionally a direction can be specified to limit the hook to one motion 
      direction: positive (+1), negative (-1) or for both (0).

    Configuration example:

    .. code-block:: yaml

        name: ccm_brake
        class: WagoAirHook
        module: motors.hooks
        wago: $wcid10b
        channel: ccmbrk
        channel_in:  ccmpress  # optional
        direction:   1         # optional 1/0/-1 (default: 0) 
        pre_move:
            wait:    1         # optional (default: 0s)
        post_move:
            wait:    2         # optional (default: 0s)
    """

    class SafetyError(Exception):
        pass

    def __init__(self, name, config):
        config.setdefault("pre_move")["value"] = 1
        config.setdefault("post_move")["value"] = 0
        super(WagoAirHook, self).__init__(name, config)

    def set(self, phase, motion_list):
        value = self.config[phase]["value"]
        wait = self.config[phase].get("wait", 0)
        direction = self.config.get("direction", 0)
        channel_in = self.config.get("channel_in", None)

        # A WagoHook is only attached to one axis, see WagoHook::_add_axis()
        motion = motion_list[0]
        axis_name = motion.axis.name
        # check if direction is valid
        if direction != 0 and motion.delta is None:
            raise self.SafetyError(
                "Cannot move {0!r}: direction is unknown. "
                "WagoAirHook {1} is set for {2} direction".format(
                    axis_name, self.name, ("positive" if direction == 1 else "negative")
                )
            )
        if (
            direction == 0
            or (direction > 0 and motion.delta > 0)
            or (direction < 0 and motion.delta < 0)
        ):
            log_debug(self, f"start setting {phase} value to {value}...")
            self.wago.set(self.channel, value)
            log_debug(self, f"finished setting {phase} value to {value}")
            if wait:
                log_debug(self, f"start {phase} wait ({wait})...")
                sleep(wait)
                log_debug(self, f"finished {phase} wait ({wait})...")
            # if channel_in, check it, input musst be equal to output
            if channel_in and self.wago.get(channel_in) != self.wago.get(self.channel):
                raise self.SafetyError(
                    "Cannot set air {0} for axis {1!r}, "
                    "check air pressure or the pressostat".format(
                        ("ON" if value == 1 else "OFF"), axis_name
                    )
                )

    def pre_move(self, motion_list):
        self.set("pre_move", motion_list)

    def post_move(self, motion_list):
        self.set("post_move", motion_list)
