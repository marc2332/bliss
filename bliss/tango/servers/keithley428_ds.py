# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

""" Keithley428 Current Amplifier

Class for controlling the Keithley428 current amplifier.
"""
from __future__ import absolute_import

__all__ = ["Keithley428", "main"]

# tango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import class_property, device_property
from tango import AttrQuality, AttrWriteType, DispLevel, DevState

# Additional import
from bliss.controllers.keithley428 import keithley428 as keithley
from functools import wraps


def is_cmd_allowed(disallowed):
    def is_allowed(func):
        @wraps(func)
        def rfunc(self, *args, **keys):
            if self.get_state() not in disallowed:
                return func(self, *args, **keys)
            else:
                raise Exception("Command not allowed")

        return rfunc

    return is_allowed


class Keithley428(Device):
    """
    Class for controlling the Keithley428 current amplifier.
    """

    # -----------------
    # Device Properties
    # -----------------
    url = device_property(
        dtype=str,
        doc="* `enet://<host>:<port>` for NI ENET adapter\n"
        "* `prologix://<host>:<port>` for prologix adapter",
    )
    pad = device_property(dtype=int, default_value=0, doc="primary address")
    sad = device_property(dtype=int, default_value=0, doc="secondary address")
    timeout = device_property(dtype=float, default_value=1., doc="socket timeout")
    tmo = device_property(dtype=int, default_value=13, doc="gpib time limit")
    eot = device_property(dtype=int, default_value=1)
    eos = device_property(dtype=str, default_value="\r\n")
    name = device_property(dtype=str, default_value="keithley428")

    # ---------------
    # General methods
    # ---------------

    def __init__(self, *args, **kwargs):
        self._keithley = None
        Device.__init__(self, *args, **kwargs)

    def init_device(self):
        Device.init_device(self)
        kwargs = {
            "gpib_url": self.url,
            "gpib_pad": self.pad,
            "gpib_timeout": self.timeout,
            "gpib_eos": self.eos,
        }
        self._keithley = keithley(self.name, kwargs)
        self.set_state(tango.DevState.ON)

    def always_executed_hook(self):
        pass

    def delete_device(self):
        pass

    # ----------
    # Attributes
    # ----------
    @attribute(
        label="Gain",
        dtype="int",
        fisallowed="is_attr_allowed",
        max_value=10,
        min_value=0,
        description="Numerical representation of the gain",
    )
    @DebugIt()
    def gain(self):
        gain, gainstr = self._keithley.Gain
        return gain

    @gain.write
    @DebugIt()
    def gain(self, value):
        self._keithley.Gain = value

    @attribute(
        label="Gain",
        dtype="str",
        fisallowed="is_attr_allowed",
        description="The gain as displayed on the front panel",
    )
    @DebugIt()
    def gainStr(self):
        gain, gainstr = self._keithley.Gain
        return gainstr

    @attribute(
        label="Overloaded",
        dtype=bool,
        fisallowed="is_attr_allowed",
        description="Test if device is overloaded: true/false",
    )
    @DebugIt()
    def overloaded(self):
        return self._keithley.Overloaded

    @attribute(
        label="Zero check",
        dtype=str,
        fisallowed="is_attr_allowed",
        description="State of Zero check: Off/On/Zero correct last sent",
    )
    @DebugIt()
    def zeroCheck(self):
        return self._keithley.ZeroCheck

    @attribute(
        label="Filter state",
        dtype=str,
        fisallowed="is_attr_allowed",
        description="State of the manual filter: Off/On",
    )
    @DebugIt()
    def filterState(self):
        return self._keithley.FilterState

    @attribute(
        label="Auto filter state",
        dtype=str,
        fisallowed="is_attr_allowed",
        description="State of the auto Filter",
    )
    @DebugIt()
    def autoFilterState(self):
        return self._keithley.AutoFilterState

    @attribute(
        label="Filter rise time",
        dtype=int,
        fisallowed="is_attr_allowed",
        max_value=9,
        min_value=0,
        description="Numerical representation of the filter rise time",
    )
    @DebugIt()
    def filterRiseTime(self):
        riseTime, riseTimeStr = self._keithley.FilterRiseTime
        return riseTime

    @filterRiseTime.write
    @DebugIt()
    def filterRiseTime(self, value):
        self._keithley.FilterRiseTime = value

    @attribute(
        label="Rise time string",
        dtype=str,
        fisallowed="is_attr_allowed",
        description="The filter rise time as displayed on the front panel",
    )
    @DebugIt()
    def filterRiseTimeStr(self):
        riseTime, riseTimeStr = self._keithley.FilterRiseTime
        return riseTimeStr

    @attribute(
        label="Voltage bias",
        dtype=float,
        fisallowed="is_attr_allowed",
        format="%6.4f",
        description="The programmed voltage bias value",
    )
    @DebugIt()
    def voltageBias(self):
        return self._keithley.VoltageBias

    @voltageBias.write
    def voltageBias(self, value):
        self._keithley.VoltageBias = value

    def is_attr_allowed(self, attr):
        return self.get_state() not in [DevState.FAULT]

    # --------
    # Commands
    # --------
    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def PerformZeroCorrect(self):
        self._keithley.PerformZeroCorrect

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def ZeroCheckOff(self):
        self._keithley.ZeroCheckOff

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def ZeroCheckOn(self):
        self._keithley.ZeroCheckOn

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def FilterOn(self):
        self._keithley.FilterOn

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def FilterOff(self):
        self._keithley.FilterOff

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def AutoFilterOn(self):
        self._keithley.AutoFilterOn
        pass

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def AutoFilterOff(self):
        self._keithley.AutoFilterOff

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def VoltageBiasOff(self):
        self._keithley.VoltageBiasOff

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def VoltageBiasOn(self):
        self._keithley.VoltageBiasOn

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def CurrentSuppressOn(self):
        self._keithley.CurrentSuppressOn

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def CurrentSuppressOff(self):
        self._keithley.CurrentSuppressOff

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def PerformAutoSuppress(self):
        self._keithley.PerformAutoSuppress

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def DisableAutoRange(self):
        self._keithley.DisableAutoRange

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def EnableAutoRange(self):
        self._keithley.EnableAutoRange

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def X10GainOff(self):
        self._keithley.X10GainOff

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def X10GainOn(self):
        self._keithley.X10GainOn


# ----------
# Run server
# ----------


def main():
    from tango import GreenMode
    from tango.server import run

    run([Keithley428], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
