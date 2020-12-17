# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss controller for ethernet NewFocus 87xx series piezo controller.
A. Beteva, M. Guijarro, ESRF BCU
"""

import time
from warnings import warn

from bliss.controllers.motor import Controller
from bliss.common.axis import AxisState
from bliss.comm.util import get_comm, TCP
from bliss.common import event
from bliss.config.settings import SimpleSetting
from bliss import global_map
import gevent.lock

DELAY = 0.02  # delay between 2 commands


class NF8753(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.__current_selected_channel = None
        self.lock = gevent.lock.RLock()

    def initialize(self):
        # acceleration is not mandatory in config
        self.axis_settings.config_setting["acceleration"] = False

        try:
            self.sock = get_comm(self.config.config_dict, TCP, port=23)
        except ValueError:
            host = self.config.get("host")
            warn("'host' keyword is deprecated. Use 'tcp' instead", DeprecationWarning)
            comm_cfg = {"tcp": {"url": host}}
            self.sock = get_comm(comm_cfg, port=23)

        global_map.register(self, children_list=[self.sock])

        if "=2" in self._write_read(None, "DRT", raw=True):
            raise RuntimeError(
                "Uncompatible closed-loop driver detected in daisy chain"
            )

    def finalize(self):
        self.sock.close()
        # this controller can't reconnect immediately
        # after socket is disconnected, so we put a delay here to make sure
        # socket is really closed on the controller side
        time.sleep(5 * DELAY)

    def initialize_axis(self, axis):
        axis.driver = axis.config.get("driver", str)
        axis.channel = axis.config.get("channel", int)
        axis.accumulator = SimpleSetting(f"{axis.name}_accumulator", default_value=0.0)
        axis.no_offset = True

        # self._write_no_reply(axis, "JOF") #, raw=True)
        self._write_no_reply(None, "MON %s" % axis.driver)

    def _select_channel(self, axis):
        change_channel = "CHL %s=%d" % (axis.driver, axis.channel)
        if change_channel != self.__current_selected_channel:
            self.__current_selected_channel = change_channel
            self._write_no_reply(None, change_channel)

    def _write_no_reply(self, axis, cmd_string):
        with self.lock:
            if not cmd_string.endswith("\r\n"):
                cmd_string += "\r\n"
            if axis is not None:
                self._select_channel(axis)
            self.sock.write_readline(cmd_string.encode(), eol=b">")
            time.sleep(DELAY)

    def _write_read(self, axis, cmd_string, eol="\r\n>", raw=False):
        with self.lock:
            if not cmd_string.endswith("\r\n"):
                cmd_string += "\r\n"

            if axis is not None:
                self._select_channel(axis)

            ans = self.sock.write_readline(cmd_string.encode(), eol=eol.encode())
            time.sleep(DELAY)

            ans = ans.decode()
            ans = ans.replace(">", "")
            if raw:
                return ans
            else:
                return ans.split("=")[1].split("\r\n>")[0]

    def read_position(self, axis):
        return axis.accumulator.get()

    def set_position(self, axis, new_position):
        """Set the position of <axis> in controller to <new_position>.
        This method is called by `position` property of <axis>.
        """
        axis.accumulator.set(new_position)
        return new_position

    def read_velocity(self, axis):
        return int(self._write_read(None, "VEL %s %d" % (axis.driver, axis.channel)))

    def set_velocity(self, axis, new_velocity):
        self._write_no_reply(
            None, "VEL %s %s=%d" % (axis.driver, axis.channel, new_velocity)
        )
        return self.read_velocity(axis)

    def state(self, axis):
        sta = self._write_read(axis, "STA", eol="\r\n>", raw=True)
        for line in sta.split("\n"):
            if line.startswith(axis.driver):
                status_byte = int(line.split("=")[-1], 16)
                if status_byte & 0x0000001:
                    return AxisState("MOVING")
                else:
                    return AxisState("READY")

    def start_one(self, motion):
        new_position = motion.axis.accumulator.get() + motion.delta
        motion.axis.accumulator.set(new_position)
        self._write_no_reply(
            motion.axis, "REL %s=%d G" % (motion.axis.driver, motion.delta)
        )

    def stop(self, axis):
        self._write_no_reply(axis, "HAL")
