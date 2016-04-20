# -*- coding: utf-8 -*-
#
# This file is part of the LinkamDsc project
#
# 
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Linkam T94

Class for controlling the Linkam T94 with Dsc stage.
"""

__all__ = ["LinkamDsc", "main"]

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import class_property, device_property
from PyTango import AttrQuality, AttrWriteType, DispLevel, DevState
# Additional import
from bliss.controllers.temperature.linkam import LinkamDsc as linkam
from functools import wraps
import numpy

def is_cmd_allowed(disallowed) :
    def is_allowed(func):
        @wraps(func)
        def rfunc(self,*args,**keys) :
            if self.get_state() not in disallowed:
                return func(self,*args,**keys)
            else:
                raise Exception("Command not allowed")
        return rfunc
    return is_allowed

class LinkamDsc(Device):
    """
    Class for controlling the Linkam T94.
    """
    __metaclass__ = DeviceMeta

    # -----------------
    # Device Properties
    # -----------------
    url = device_property(dtype=str, doc='use rfc2217://lid30b2:28010')
    name = device_property(dtype=str, default_value="linkam")

    # ---------------
    # General methods
    # ---------------

    def __init__(self, *args, **kwargs):
        self._linkam = None
        Device.__init__(self, *args, **kwargs)

    def init_device(self):
        Device.init_device(self)
        kwargs = {
                  'serial_url': self.url,
        }
#        self._linkam = linkam(self.name, kwargs)
        self.set_state(PyTango.DevState.ON)

    def always_executed_hook(self):
        pass

    def delete_device(self):
        pass

    # ----------
    # Attributes
    # ----------
    @attribute(label='Ramp number', dtype='int', fisallowed="is_attr_allowed",
        description="Current profile ramp number")
    @DebugIt()
    def rampNumber(self):
        return self._linkam.rampNumber

    @attribute(label='Ramp limit', dtype='float', fisallowed="is_attr_allowed",
        description="Current profile ramp temperature limit")
    @DebugIt()
    def rampLimit(self):
        return self._linkam.rampLimit

    @attribute(label='Ramp hold time', dtype='float', fisallowed="is_attr_allowed",
        description="Current profile ramp hold time (sec)")
    @DebugIt()
    def rampHoldTime(self):
        return self._linkam.rampHoldTime

    @attribute(label='Ramp rate', dtype='float', fisallowed="is_attr_allowed",
        description="Current profile ramp rate (degrees/min)")
    @DebugIt()
    def rampRate(self):
        return self._linkam.rampRate

    @attribute(label='Temperature', dtype='float', fisallowed="is_attr_allowed",
        description="Current temperature")
    @DebugIt()
    def temperature(self):
        return self._linkam.getTemperature

    @attribute(label='Pump speed', dtype='int', fisallowed="is_attr_allowed",max_value=30, min_value=0,
        description="Liquid nitrogen pump speed")
    @DebugIt()
    def pumpSpeed(self):
        return self._linkam.pumpSpeed

    @pumpSpeed.write
    @DebugIt()
    def pumpSpeed(self, value):
        self._linkam.pumpSpeed = value

    @attribute(label='Dsc Sample Rate', dtype='float', fisallowed="is_attr_allowed",max_value=150.0, min_value=0.3,
        description="DSC sampling rate")
    @DebugIt()
    def dscSamplingRate(self):
        return self._linkam.dscSamplingRate

    @dscSamplingRate.write
    @DebugIt()
    def dscSamplingRate(self, value):
        self._linkam.dscSamplingRate= value

    def is_attr_allowed(self, attr):
        return self.get_state() not in [DevState.FAULT]

    # --------
    # Commands
    # --------
    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def ClearBuffer(self):
        self._linkam.clearBuffer

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def Hold(self):
        self._linkam.hold

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def Start(self):
        self._linkam.start

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def Stop(self):
        self._linkam.stop

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def PumpAutomatic(self):
        self._linkam.setPumpAutomatic

    @command
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def PumpManual(self):
        self._linkam.setPumpManual

    @command(dtype_in=[float,], doc_in=' ramp list')
    @DebugIt()
    @is_cmd_allowed([DevState.FAULT, DevState.OFF, DevState.UNKNOWN])
    def Profile(self, ramps):
        print ramps.size
        ramps = numpy.ndarray((3,3), buffer=ramps ,dtype=float)
        self._linkam.profile

    
# ----------
# Run server
# ----------

def main():
    from PyTango import GreenMode
    from PyTango.server import run
    run([LinkamDsc,], green_mode=GreenMode.Gevent)

if __name__ == '__main__':
    main()
