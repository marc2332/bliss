# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.motor import Controller
from bliss.controllers import _leica_usb as leica_usb
from bliss.common.axis import AxisState
from bliss.common import log
from bliss.common import event
import sys


class leica(Controller):
    def __init__(self, *args, **kwargs):
        Controller.__init__(self, *args, **kwargs)

        self.usb_controller = None

    def __del__(self):
        try:
            self.usb_controller.close()
        except Exception:
            sys.excepthook(*sys.exc_info())

    def initialize(self):
        # velocity and acceleration are not mandatory in config
        self.axis_settings.config_setting["velocity"] = False
        self.axis_settings.config_setting["acceleration"] = False
        try:
            self.usb_controller = leica_usb.LeicaFocus()
        except Exception:
            sys.excepthook(*sys.exc_info())
            raise RuntimeError(
                "Could not initialize Leica controller (hint: is microscope switched on ? Or try to re-plug USB)"
            )

    def finalize(self):
        if self.usb_controller:
            self.usb_controller.close()

    def initialize_axis(self, axis):
        pass

    def read_position(self, axis):
        mot_num = axis.config.get("channel", int)
        if self.state(axis) == "MOVING":
            return 0
        return self.usb_controller.read_mot_pos(mot_num)

    def state(self, axis):
        mot_num = axis.config.get("channel", int)
        # print 'calling state for',mot_num
        if self.usb_controller.curr_move and not self.usb_controller.curr_move.ready():
            return AxisState("MOVING")
        mot_group = self.usb_controller.read_mot_pos_status(mot_num)
        for mot, pos, state in mot_group:
            if mot == mot_num:
                if state & self.usb_controller.MOT_STA_MOV:
                    return AxisState("MOVING")
                elif state & self.usb_controller.MOT_STA_LIMN:
                    return AxisState("READY", "LIMNEG")
                elif state & self.usb_controller.MOT_STA_LIMP:
                    return AxisState("READY", "LIMPOS")
                else:
                    return AxisState("READY")

    def stop(self, axis):
        pass

    def start_one(self, motion):
        axis = motion.axis
        mot_num = axis.config.get("channel", int)
        self.usb_controller.start_mot_move(mot_num, motion.target_pos, False)
