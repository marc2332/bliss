# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import serial

from bliss.controllers.motor import Controller
from bliss.comm.util import get_comm
from bliss.common import log as elog

from bliss.common.axis import AxisState


"""
Bliss controller for XXX.
"""


class XXX(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

    def initialize(self):
        """
        """
        self.comm = get_comm(self.config)

    def finalize(self):
        """
        """
        self.comm.close()

    def initialize_axis(self, axis):
        """
        Reads specific config
        Adds specific methods
        """

    def read_position(self, axis):
        """
        Returns position's setpoint or measured position.

        Args:
            - <axis> : bliss axis.
            - [<measured>] : boolean : if True, function returns
              measured position in ???
        Returns:
            - <position> : float : axis setpoint in ???.
        """
        raise NotImplementedError

    def read_encoder(self, encoder):
        raise NotImplementedError

    def read_velocity(self, axis):
        """
        Args:
            - <axis> : Bliss axis object.
        Returns:
            - <velocity> : float
        """

    def set_velocity(self, axis, new_velocity):
        pass

    def state(self, axis):
        _ans = "whatever"
        if _ans == "moving":
            return AxisState("MOVING")
        else:
            return AxisState("READY")

    def prepare_move(self, motion):
        pass

    def start_one(self, motion):
        """
        """
        self.comm.write("MOVE")

    def stop(self, axis):
        # Halt a scan (not a movement ?)
        self.comm.write("STOP")

    def raw_write(self, axis, cmd):
        self.comm.write(cmd)

    def raw_write_read(self, axis, cmd):
        return self.comm.write_readline(cmd)

    def get_id(self, axis):
        """
        Returns firmware version.
        """
        return self.comm.write_readline("?VER")

    def get_info(self, axis):
        """
        Returns information about controller.
        """
        return ""
