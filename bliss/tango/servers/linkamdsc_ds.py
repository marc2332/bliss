# -*- coding: utf-8 -*-
#
# This file is part of the LinkamDsc project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Linkam T94/T95

Class for controlling the Linkam T94 with Dsc stage.
"""


import numpy
from functools import wraps

# tango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import class_property, device_property
from tango import AttrQuality, AttrWriteType, DispLevel, DevState

import gevent
from gevent import lock

# Additional import
from bliss.controllers.temperature.linkam import LinkamDsc as linkam
from bliss.controllers.temperature.linkam import LinkamScan as linkamScan

__all__ = ["LinkamDsc", "main"]


def is_cmd_allowed(fisallowed):
    def is_allowed(func):
        @wraps(func)
        def rfunc(self, *args, **keys):
            if getattr(self, fisallowed)():
                return func(self, *args, **keys)
            else:
                raise Exception("Command not allowed")

        return rfunc

    return is_allowed


class LinkamDsc(Device):
    """
    Class for controlling the Linkam T94.
    """

    # -----------------
    # Device Properties
    # -----------------
    SerialUrl = device_property(dtype=str, doc="use rfc2217://ld262:28068")
    Name = device_property(dtype=str, default_value="linkam")

    # ---------------
    # General methods
    # ---------------

    def __init__(self, *args, **kwargs):
        self._linkam = None
        Device.__init__(self, *args, **kwargs)

    def init_device(self):
        Device.init_device(self)
        config = {"serial_url": self.SerialUrl}
        self._linkam = linkam(self.Name, config)
        self._lock = lock.Semaphore()
        self._filename = ""
        self._profileData = [0.0, 0.0, 0.0]
        self._linkam.subscribe(self._profileCompleteCallback)
        if self._linkam is not None:
            attr = self.get_device_attr().get_attr_by_name("temperature")
            attr.set_write_value(self._linkam.getTemperature())
        self.set_state(tango.DevState.ON)

    def always_executed_hook(self):
        pass

    def delete_device(self):
        pass

    # ----------
    # Attributes
    # ----------
    @attribute(
        label="Ramp number",
        dtype="int",
        fisallowed="is_attr_allowed",
        description="Current profile ramp number",
    )
    @DebugIt()
    def rampNumber(self):
        return self._linkam.rampNumber

    @attribute(
        label="Ramp limit",
        dtype="float",
        fisallowed="is_attr_allowed",
        description="Current profile ramp temperature limit",
    )
    @DebugIt()
    def rampLimit(self):
        return self._linkam.rampLimit

    @attribute(
        label="Ramp hold time",
        dtype="float",
        fisallowed="is_attr_allowed",
        description="Current profile ramp hold time (sec)",
    )
    @DebugIt()
    def rampHoldTime(self):
        return self._linkam.rampHoldTime

    @attribute(
        label="Ramp rate",
        dtype="float",
        fisallowed="is_attr_allowed",
        description="Current profile ramp rate (degrees/min)",
    )
    @DebugIt()
    def rampRate(self):
        return self._linkam.rampRate

    @rampRate.write
    def rampRate(self, rate):
        self._linkam.rampRate = rate

    @attribute(
        label="Temperature",
        dtype="float",
        fisallowed="is_attr_allowed",
        description="Current temperature",
    )
    @DebugIt()
    def temperature(self):
        return self._linkam.getTemperature()

    @temperature.write
    def temperature(self, temp):
        self._linkam.setTemperature(temp)

    @attribute(
        label="DSC data",
        dtype=["float"],
        fisallowed="is_attr_allowed",
        max_dim_x=3,
        description="Current temperature and dsc data",
    )
    @DebugIt()
    def dscData(self):
        return self._linkam.getDscData()

    @attribute(
        label="Pump speed",
        dtype="int",
        fisallowed="is_attr_allowed",
        max_value=30,
        min_value=0,
        description="Liquid nitrogen pump speed (0-30)",
    )
    @DebugIt()
    def pumpSpeed(self):
        return self._linkam.pumpSpeed

    @pumpSpeed.write
    @DebugIt()
    def pumpSpeed(self, value):
        self._linkam.pumpSpeed = value

    @attribute(
        label="Filename",
        dtype="str",
        fisallowed="is_attr_allowed",
        description="Output dataset filename. Data will not be saved if not specified",
    )
    @DebugIt()
    def filename(self):
        return self._filename

    @filename.write
    @DebugIt()
    def filename(self, value):
        self._filename = value

    @attribute(
        label="Polling time",
        dtype="float",
        fisallowed="is_attr_allowed",
        description="Polling time (seconds): adjust with care, must be less than sampling time for dsc",
    )
    @DebugIt()
    def pollTime(self):
        return self._linkam.pollTime

    @pollTime.write
    @DebugIt()
    def pollTime(self, time):
        self._linkam.pollTime = time

    @attribute(
        label="Starting Ramp",
        dtype="int",
        fisallowed="is_attr_allowed",
        description="Ramp number when acquisition will start",
    )
    @DebugIt()
    def startingRamp(self):
        return self._linkam.startingRamp

    @startingRamp.write
    @DebugIt()
    def startingRamp(self, rampNos):
        self._linkam.startingRamp = rampNos

    @attribute(
        label="Profile Data",
        dtype=["float"],
        fisallowed="is_attr_allowed",
        max_dim_x=999,
        description="Profile ramp data comprising rate, temp and dwell",
    )
    @DebugIt()
    def profileData(self):
        return self._profileData

    @profileData.write
    @DebugIt()
    def profileData(self, profile):
        self._profileData = profile

    @attribute(
        label="Dsc Sample Rate",
        dtype="float",
        fisallowed="is_attr_allowed",
        max_value=150.0,
        min_value=0.3,
        description="DSC sampling rate: allowable values are (.3, .6, .9, 1.5, 3, 6, 9, 15, 30, 60, 90, or 150)",
    )
    @DebugIt()
    def dscSamplingRate(self):
        return self._linkam.dscSamplingRate

    @dscSamplingRate.write
    @DebugIt()
    def dscSamplingRate(self, value):
        self._linkam.dscSamplingRate = value

    @attribute(
        label="Linkam status",
        dtype="str",
        fisallowed="is_attr_allowed",
        description="Current linkam status: Heating/Cooling/Holding/Stopped",
    )
    @DebugIt()
    def acqStatus(self):
        return self._linkam.status()

    def is_attr_allowed(self, attr):
        return self.get_state() not in [DevState.FAULT, DevState.OFF]

    # --------
    # Commands
    # --------
    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def ClearBuffer(self):
        self._linkam.clearBuffer()

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def Hold(self):
        self._linkam.hold()
        self.set_state(tango.DevState.ON)

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def Start(self):
        self._linkam.start()
        self.set_state(tango.DevState.RUNNING)

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def Stop(self):
        self._linkam.stop()
        self.set_state(tango.DevState.ON)

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def PumpAutomatic(self):
        self._linkam.setPumpAutomatic()

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def PumpManual(self):
        self._linkam.setPumpManual()

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def Profile(self):
        rr = numpy.ndarray(
            (len(self._profileData) / 3, 3), buffer=self._profileData, dtype=float
        )
        ramplist = [tuple(a) for a in rr]
        print(ramplist)
        if self._filename:
            self._scan = linkamScan(self._linkam, self._filename)
        self._linkam.profile(ramplist)
        self.set_state(tango.DevState.RUNNING)

    def is_command_allowed(self):
        return self.get_state() not in [DevState.FAULT, DevState.OFF, DevState.UNKNOWN]

    def _profileCompleteCallback(self):
        self.set_state(tango.DevState.ON)


# ----------
# Run server
# ----------


def main():
    from tango import GreenMode
    from tango.server import run

    run([LinkamDsc], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
