# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
EMBL Microdiff MD2S set of methods

yml configuration example:
   name: diffractometer
   class: MD2S
   exporter_addr: 'microdiff29new:9001'
"""

import time
from bliss.common.task import task
from bliss.common.utils import grouped
from bliss.comm.Exporter import *
import functools


class MD2S(object):
    def __init__(self, name, config):
        self.phases = {
            "Centring": 1,
            "BeamLocation": 2,
            "DataCollection": 3,
            "Transfer": 4,
        }
        self.timeout = 3  # s by default
        nn, port = config.get("exporter_addr").split(":")
        self._exporter = Exporter(nn, int(port))

        fshutter = config.get("fshutter")
        if fshutter:
            fshutter.set_external_control(
                functools.partial(
                    self._exporter.writeProperty, "FastShutterIsOpen", "true"
                ),
                functools.partial(
                    self._exporter.writeProperty, "FastShutterIsOpen", "false"
                ),
                lambda: self._exporter.readProperty("FastShutterIsOpen") == "true",
            )

    def get_hwstate(self):
        """Read the hardware state (if implemented)
           Returns:
             state(str): the hardware state or Ready (if not implemented)
        """
        try:
            return self._exporter.readProperty("HardwareState")
        except Exception:
            return "Ready"

    def get_swstate(self):
        """Read the software state.
           Returns:
             state(str): the software state
        """
        return self._exporter.readProperty("State")

    def _ready(self):
        if self.get_hwstate() == "Ready" and self.get_swstate() == "Ready":
            return True
        return False

    def _wait_ready(self, timeout=None):
        if timeout <= 0:
            timeout = self.timeout
        tt1 = time.time()
        while time.time() - tt1 < timeout:
            if self._ready():
                break
            else:
                time.sleep(0.5)

    def get_phase(self):
        """Read the current phase
           Returns:
             phase(str): the current phase (Centring, BeamLocation,
                            DataCollection or Transfer)
        """
        return self._exporter.readProperty("CurrentPhase")

    def set_phase(self, phase, wait=False, timeout=40):
        """Set new phase. Wait until finished.
           Args:
               phase(str): Centring, BeamLocation, DataCollection or Transfer
               wait(bool): Wait until finished (True/False)
               timeout(float): wait time [s]
           Returns:
            None
        """
        if phase in self.phases:
            self._exporter.execute("startSetPhase", phase)
            if wait:
                self._wait_ready(timeout)

    def get_camera_calibration(self):
        """Read the pixel per mm - the values are different for each zoom level
           Returns:
             values(list): pixel per mm on Y and Z axis
        """
        # the value depends on the zoom
        px_mm_y = 1. / self._exporter.readProperty("CoaxCamScaleX")
        px_mm_z = 1. / self._exporter.readProperty("CoaxCamScaleY")
        return [px_mm_y, px_mm_z]

    def move_motors(self, *args):
        """Simultaneous move for all the listed motors.
           Args:
             motor,position(list): motor_object0, position0, motor_object1, ...
        """
        par = ""
        for axis, target in grouped(args, 2):
            par += "%s=%f," % (axis.root_name, target)
        self._exporter.execute("startSimultaneousMoveMotors", par)
        self._wait_ready(20)

    @task
    def _simultaneous_move(self, *args):
        axis_list = []
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            axis.move(target, wait=False)
        return [axis.wait_move() for axis in axis_list]

    @task
    def _simultaneous_rmove(self, *args):
        axis_list = []
        for axis, target in grouped(args, 2):
            axis_list.append(axis)
            axis.rmove(target, wait=False)
        return [axis.wait_move() for axis in axis_list]

    def msopen(self):
        """Open fast shutter"""
        self._exporter.writeProperty("FastShutterIsOpen", "true")

    def msclose(self):
        """Close fast shutter"""
        self._exporter.writeProperty("FastShutterIsOpen", "false")

    def fldetin(self):
        """Move the fluorescense detector close to the beam position"""
        self._exporter.writeProperty("FluoDetectorIsBack", "false")

    def fldetout(self):
        """Move the fluorescense detector far from the beam position"""
        self._exporter.writeProperty("FluoDetectorIsBack", "true")

    def fldetstate(self):
        """Read the fluorescense detector position
           Returns:
             position(bool): close to the beam - True/False
        """
        self._exporter.readProperty("FluoDetectorIsBack")

    def flight(self, state=None):
        """Switch the front light on/off or read the state
           Args:
             state(bool): on (True), off (False) or None (read only)
           Returns:
             state(bool): on (True)or off (False) - when no args
        """
        if state:
            self._exporter.writeProperty("FrontLightIsOn", state)
        else:
            return self._exporter.readProperty("FrontLightIsOn")

    def blight(self, state=None):
        """Switch the back light on/off or read the state
           Args:
             state(bool): on (True), off (False) or None (read only)
           Returns:
             state(bool): on (True)or off (False) - when no args
        """
        if state:
            self._exporter.writeProperty("BackLightIsOn", state)
        else:
            return self._exporter.readProperty("BackLightIsOn")

    def cryo(self, state=None):
        """Set the cryostat close to/far from the sample or read the position
           Args:
             state(bool): close to (True), far from (False) or None (read only)
           Returns:
             state(bool): close to(True) or far from(False) - when no args
        """
        if state:
            self._exporter.writeProperty("CryoIsBack", state)
        else:
            return self._exporter.readProperty("CryoIsBack")

    def microdiff_init(self, wait=True):
        """Do the homing of all the motors
           Args:
             wait(bool): Wait until finished (True/False)
        """
        self._exporter.execute("startHomingAll")
        if wait:
            self._wait_ready(60)

    def diffractometer_init(self, wait=True):
        self.microdiff_init(wait)

    def phi_init(self, wait=True):
        """Do the homing of omega
           Args:
             wait(bool): Wait until finished (True/False)
        """
        self._exporter.execute("startHomingMotor", "Omega")
        if wait:
            self._wait_ready(10)

    def zoom_init(self, wait=True):
        """Do the homing of the zoom
           Args:
             wait(bool): Wait until finished (True/False)
        """
        self._exporter.execute("startHomingMotor", "Zoom")
        if wait:
            self._wait_ready(10)

    def kappa_init(self, wait=True):
        """Do the homing of the kappa
           Args:
             wait(bool): Wait until finished (True/False)
        """
        self._exporter.execute("startHomingMotor", "Kappa")
        if wait:
            self._wait_ready(10)

        self._exporter.execute("startHomingMotor", "Phi")
        if wait:
            self._wait_ready(10)

    def prepare(self, what, **kwargs):
        """Do actions to prepare the MD2S to use in different procedures like
           centrebeam or alignment. Wait until actions done.
           Args:
             what(string): which is action to follow (see_beam, data_collect)
           Keyword Args:
             zoom_level(int): where to move the zoom to
           Returns:
             zoom_level(int): position before the execition of the action,
                              if relevant
        """
        if what == "data_collect":
            self.set_phase("DataCollection", wait=True, timeout=100)
            if "zoom_level" in kwargs:
                self._exporter.writeProperty(
                    "CoaxialCameraZoomValue", kwargs["zoom_level"]
                )
                self._wait_ready(20)

        if what == "see_beam":
            zoom_level = kwargs.get("zoom_level", 5)
            self.set_phase("BeamLocation", wait=True, timeout=100)
            self._exporter.writeProperty("CapillaryPosition", "OFF")
            self._wait_ready(20)
            self._exporter.writeProperty("AperturePosition", "OFF")
            self._wait_ready(20)
            # get the current zoom position and move zoom to zoom_level
            curr_zoom = self._exporter.readProperty("CoaxialCameraZoomValue")
            self._exporter.writeProperty("CoaxialCameraZoomValue", zoom_level)
            self._wait_ready(20)
            return curr_zoom
