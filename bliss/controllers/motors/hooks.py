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
