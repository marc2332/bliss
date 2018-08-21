# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import weakref
import struct
import numpy

from bliss.config.channels import Cache
from bliss.common.shutter import Shutter as BaseShutter
from . import _ackcommand


class Shutter(BaseShutter):
    """
    IcePAP shutter.
    Basic configuration:
        name: fastshutter
        axis_name: mot_name            #axis name
        external-control: $wago_switch #external control reference (not mandatory)
        closed_position: 1             # the closed position (in user position)
        opened_position: 2             # the opened position (in user position)
    """

    @property
    def axis(self):
        if self.mode == self.CONFIGURATION:
            return self._axis
        else:
            raise RuntimeError(
                "Shutter %s is not in configuration mode, "
                " please switch to that mode before asking "
                " the reference axis" % self.name
            )

    @property
    def closed_position(self):
        return self.settings.get("closed_position", self.config.get("closed_position"))

    @closed_position.setter
    def closed_position(self, position):
        if self.mode != self.CONFIGURATION:
            raise RuntimeError(
                "Shutter %s: can set the closed position, "
                "not in Configuration mode" % self.name
            )
        self.settings.set("closed_position", position)

    @property
    def opened_position(self):
        return self.settings.get("opened_position", self.config.get("opened_position"))

    @opened_position.setter
    def opened_position(self, position):
        if self.mode != self.CONFIGURATION:
            raise RuntimeError(
                "Shutter %s: can set the opened position, "
                "not in Configuration mode" % self.name
            )
        self.settings.set("opened_position", position)

    def __init__(self, name, controller, config):
        BaseShutter.__init__(self, name, config)
        self.__controller = weakref.proxy(controller)
        self._axis = None
        self._position_loaded = Cache(
            self, "loaded-position", default_value=(None, None)
        )

    def _init(self):
        axis_name = self.config.get("axis_name")
        if axis_name is not None:
            self._axis = self.__controller.get_axis(axis_name)
            self._axis.position()  # real init
        else:
            raise RuntimeError("Shutter %s has no axis_name configured" % self.name)

    def _initialize_hardware(self):
        # will trigger _set_mode
        self.mode = self.mode

    def _set_mode(self, mode):
        self._axis.activate_tracking(False)

        if mode == self.EXTERNAL:
            ext_ctrl = self.external_control
            if ext_ctrl is not None:
                ext_ctrl.set("CLOSED")
            else:
                raise RuntimeError(
                    "Mode is External but no external control object, aborting"
                )

            closed_position = self.closed_position
            if closed_position is None:
                raise RuntimeError(
                    "Shutter %s hasn't been configured, "
                    "missing closed_position" % self.name
                )
            opened_position = self.settings.get(
                "opened_position", self.config.get("opened_position")
            )
            if opened_position is None:
                raise RuntimeError(
                    "Shutter %s hasn't been configured, "
                    "missing opened_position" % self.name
                )
            self._load_position(closed_position, opened_position)
            self._axis.activate_tracking(True)

    def _load_position(self, closed_position, opened_position):
        current_closed, current_opened = self._position_loaded.value
        if current_closed != closed_position or current_opened != opened_position:
            self._axis.set_tracking_positions(
                [closed_position, opened_position], cyclic=True
            )
            self.settings.update(
                {"closed_position": closed_position, "opened_position": opened_position}
            )
            self._position_loaded.value = (closed_position, opened_position)

    def _opening_time(self):
        return self._move_time()

    def _closing_time(self):
        return self._move_time()

    def _move_time(self):
        acctime = self._axis.acctime()
        velocity = self._axis.velocity()
        acceleration_distance = velocity * acctime
        total_distance = abs(self.opened_position - self.closed_position)
        if acceleration_distance > total_distance:
            return 2 * math.sqrt(total_distance / self._axis.acceleration())
        else:
            t1 = (total_distance - acceleration_distance) / velocity
            return t1 + 2 * acctime

    def _measure_open_close_time(self):
        tmove = self._move_time()
        return tmove, tmove

    def _open(self):
        open_pos = self.opened_position
        if open_pos is None:
            raise RuntimeError(
                "Shutter %s hasn't been configured, "
                "missing opened_position" % self.name
            )

        self._axis.move(open_pos)

    def _close(self):
        closed_pos = self.closed_position
        if closed_pos is None:
            raise RuntimeError(
                "Shutter %s hasn't been configured, "
                "missing closed_position" % self.name
            )

        self._axis.move(closed_pos)

    def _state(self):
        curr_pos = self._axis.position()
        if curr_pos == self.closed_position:
            return self.CLOSED
        elif curr_pos == self.opened_position:
            return self.OPEN
        else:
            return self.UNKNOWN
