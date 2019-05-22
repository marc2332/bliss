# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
ID31 motion hook for the carnac motors.
"""

import gevent
from bliss.common.hook import MotionHook


class CarnacHook(MotionHook):
    """
    Motion hook specific for ID31 carnac motors.

    Configuration example:

    .. code-block:: yaml

        hooks:
          - name: carnac_hook
            class: CarnacHook
            module: motors.hooks
            plugin: bliss
        controllers:
          - name: ice313
            class: IcePAP
            host: iceid313
            plugin: emotion
            axes:
              - name: cncx
                motion_hooks:
                  - $carnac_hook
              - name: cncy
                motion_hooks:
                  - $carnac_hook
              - name: cncz
                motion_hooks:
                  - $carnac_hook
    """

    def __init__(self, name, config):
        self.config = config
        self.name = name
        super(CarnacHook, self).__init__()

    def _wait_ready(self, axes):
        with gevent.Timeout(1, RuntimeError("not all motors ready after timeout")):
            while True:
                ready = [axis for axis in axes if axis.hw_state.READY]
                if len(ready) == len(axes):
                    break
        self._logger.debug("All motors ready!")

    def pre_move(self, motion_list):
        axes = [motion.axis for motion in motion_list]
        axes_names = ", ".join([axis.name for axis in axes])
        self._logger.debug("Start power ON for %s", axes_names)
        tasks = [gevent.spawn(axis.controller.set_on, axis) for axis in axes]
        gevent.joinall(tasks, timeout=1, raise_error=True)
        self._logger.debug("Finished power ON for %s", axes_names)
        # we know empirically that the carnac takes ~1.3s to reply it is
        # ready after a power on
        gevent.sleep(1.2)
        self._wait_ready(axes)

    def post_move(self, motion_list):
        axes = [motion.axis for motion in motion_list]
        axes_names = ", ".join([axis.name for axis in axes])
        self._logger.debug("Start power OFF for %s", axes_names)
        tasks = [gevent.spawn(axis.controller.set_off, axis) for axis in axes]
        gevent.joinall(tasks, timeout=1, raise_error=True)
        self._logger.debug("Finished power OFF for %s", axes_names)
        self._wait_ready(axes)
