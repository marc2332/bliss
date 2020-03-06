# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import time
import numpy
import struct
import logging
import threading

# tango imports
import tango
from tango import GreenMode
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property

# Add additional imports
import gevent
from gevent import lock
from functools import wraps
from bliss.controllers.nano_bpm import NanoBpm as nanoBpm
from bliss import global_map
from bliss.common.logtools import *


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


class NanoBpm(Device):

    CONTINUOUS, STREAMING = list(range(2))
    BPP8, BPP16, BPP32 = list(range(3))

    # -------------------------------------------------------------------------
    # Device Properties
    # -------------------------------------------------------------------------
    CommandUrl = device_property(dtype=str, doc="use socket://192.999.999.999:2222")
    ControlUrl = device_property(dtype=str, doc="use socket://192.999.999.999:2223")
    Name = device_property(dtype=str, default_value="NanoBpm")

    # -------------------------------------------------------------------------
    # General methods
    # -------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        self.__nanobpm = None
        Device.__init__(self, *args, **kwargs)

    @DebugIt()
    def delete_device(self):
        self._nanobpm = None

    @DebugIt()
    def init_device(self):
        Device.init_device(self)
        kwargs = {"command_url": self.CommandUrl, "control_url": self.ControlUrl}
        self._nanoBpm = nanoBpm(self.Name, kwargs)
        self._AcqMode2String = {self.CONTINUOUS: "continuous", self.STREAMING: "stream"}
        self.imageDepth2String = {
            self.BPP8: "bpp8",
            self.BPP16: "bpp16",
            self.BPP32: "bpp32",
        }
        global_map.register(
            self, children_list=[self._nanoBpm], tag=f"nanobpm_ds:{self.Name}"
        )
        self._imageDepth = self.BPP8
        self._imageData = None
        self._lock = lock.Semaphore()
        self._acqMode = self.STREAMING
        self._CoG = None
        self._xprofile = None
        self._yprofile = None
        self._xfit = None
        self._yfit = None
        # set up change events for Tango clients
        self.set_change_event("Centre", True, False)
        self.set_change_event("Xprofile", True, False)
        self.set_change_event("Yprofile", True, False)
        self.set_change_event("Xfit", True, False)
        self.set_change_event("Yfit", True, False)
        self.set_change_event("ReadImage8", True, False)
        self.set_change_event("ReadImage16", True, False)
        self.set_change_event("ReadImage32", True, False)
        self._nanoBpm.subscribe(self.bpmCallback)

        attr = self.get_device_attr().get_attr_by_name("acqMode")
        attr.set_write_value(self._AcqMode2String[self._acqMode])
        attr = self.get_device_attr().get_attr_by_name("imageDepth")
        attr.set_write_value(self.imageDepth2String[self._imageDepth])
        if self._nanoBpm is not None:
            attr = self.get_device_attr().get_attr_by_name("gain")
            attr.set_write_value(self._nanoBpm.GAIN)
            attr = self.get_device_attr().get_attr_by_name("offset")
            attr.set_write_value(self._nanoBpm.OFFSET)
            attr = self.get_device_attr().get_attr_by_name("horizMinAmp")
            attr.set_write_value(self._nanoBpm.H_MINAMP)
            attr = self.get_device_attr().get_attr_by_name("vertMinAmp")
            attr.set_write_value(self._nanoBpm.V_MINAMP)
            attr = self.get_device_attr().get_attr_by_name("vertMinRSQ")
            attr.set_write_value(self._nanoBpm.V_MINRSQ)
            attr = self.get_device_attr().get_attr_by_name("horizMinRSQ")
            attr.set_write_value(self._nanoBpm.H_MINRSQ)
            attr = self.get_device_attr().get_attr_by_name("maxIter")
            attr.set_write_value(self._nanoBpm.MAXITER)

        self.set_state(tango.DevState.ON)

    def always_executed_hook(self):
        pass

    # -------------------------------------------------------------------------
    # Attributes
    # -------------------------------------------------------------------------
    @attribute(
        label="AcqMode", dtype=str, description="Acquisition mode (continuous/stream)"
    )
    @DebugIt()
    def acqMode(self):
        return self._AcqMode2String[self._acqMode]

    @acqMode.write
    @DebugIt()
    def acqMode(self, mode):
        ind = list(self._AcqMode2String.values()).index(mode)
        self._acqMode = list(self._AcqMode2String.keys())[ind]

    @attribute(
        label="Integration time",
        dtype=float,
        unit="s",
        min_value="0.0",
        memorized=True,
        description="Integration time in seconds",
        fisallowed="is_attr_rw_allowed",
    )
    @DebugIt()
    def integrationTime(self):
        return self._nanoBpm.getIntegrationTime()

    @integrationTime.write
    @DebugIt()
    def integrationTime(self, time):
        self._nanoBpm.setIntegrationTime(time)

    @attribute(
        label=" Subtract Background",
        dtype=bool,
        memorized=True,
        fisallowed="is_attr_rw_allowed",
        description="To activate background subtraction (true = ON)",
    )
    @DebugIt()
    def subtractBackground(self):
        return self._nanoBpm.SUBTRACTDARK

    @subtractBackground.write
    @DebugIt()
    def subtractBackground(self, enable):
        self._nanoBpm.SUBTRACTDARK = 1 if enable else 0

    @attribute(
        label="NbFramesToSum",
        dtype=int,
        hw_memorized=False,
        memorized=True,
        fisallowed="is_attr_rw_allowed",
        description="Number frames to average or sum (must be power of 2. default=4",
    )
    @DebugIt()
    def nbFramesToSum(self):
        return self._nanoBpm.nbFramesToSum

    @nbFramesToSum.write
    @DebugIt()
    def nbFramesToSum(self, num):
        self._nanoBpm.nbFramesToSum = num

    @attribute(
        label="Gain",
        dtype=int,
        fisallowed="is_attr_rw_allowed",
        description="Gain of the device",
    )
    def gain(self):
        return self._nanoBpm.GAIN

    @gain.write
    def gain(self, val):
        self._nanoBpm.GAIN = val

    @attribute(
        label="Offset",
        dtype=int,
        fisallowed="is_attr_rw_allowed",
        description="Offset of the device",
    )
    def offset(self):
        return self._nanoBpm.OFFSET

    @offset.write
    def offset(self, val):
        self._nanoBpm.OFFSET = val

    @attribute(
        label="Maximum Iterations",
        dtype=int,
        fisallowed="is_attr_rw_allowed",
        description="Maximum number of iterations for the fitting algorithm",
    )
    def maxIter(self):
        return self._nanoBpm.MAXITER

    @maxIter.write
    def maxIter(self, val):
        self._nanoBpm.MAXITER = val

    @attribute(
        label="Horizontal Minimum Amplitude",
        dtype=float,
        fisallowed="is_attr_rw_allowed",
        description="",
    )
    def horizMinAmp(self):
        return self._nanoBpm.H_MINAMP

    @horizMinAmp.write
    def horizMinAmp(self, val):
        self._nanoBpm.H_MINAMP = val

    @attribute(
        label="Vertical Minimum Amplitude",
        dtype=float,
        fisallowed="is_attr_rw_allowed",
        description="Fitting minimum amplitude in vertical direction",
    )
    def vertMinAmp(self):
        return self._nanoBpm.V_MINAMP

    @vertMinAmp.write
    def vertMinAmp(self, val):
        self._nanoBpm.V_MINAMP = val

    @attribute(
        label="Vertical Minimum Chi-squared",
        dtype=float,
        fisallowed="is_attr_rw_allowed",
        description="Minimum chi-squared value for fitting in vertical direction",
    )
    def vertMinRSQ(self):
        return self._nanoBpm.V_MINRSQ

    @vertMinRSQ.write
    def vertMinRSQ(self, val):
        self._nanoBpm.V_MINRSQ = val

    @attribute(
        label="Horizontal Minimum Chi-squared",
        dtype=float,
        fisallowed="is_attr_rw_allowed",
        description="Minimum chi-squared value for fitting in horizontal direction",
    )
    def horizMinRSQ(self):
        return self._nanoBpm.H_MINRSQ

    @horizMinRSQ.write
    def horizMinRSQ(self, val):
        self._nanoBpm.H_MINRSQ = val

    #    @attribute(label="Last frame number acquired", dtype=int, fisallowed="is_attr_allowed",
    #               description="")
    #    @DebugIt()
    #    def last_image_acquired(self):
    #        return -1 if self._imageData is None else self._imageData[0]

    @attribute(
        label="Image depth", dtype=str, fisallowed="is_attr_allowed", description=""
    )
    @DebugIt()
    def imageDepth(self):
        return self.imageDepth2String[self._imageDepth]

    @imageDepth.write
    def imageDepth(self, depth):
        try:
            ind = list(self.imageDepth2String.values()).index(depth)
            self._imageDepth = list(self.imageDepth2String.keys())[ind]
        except ValueError:
            pass

    @attribute(
        label="Centre",
        dtype=[float],
        fisallowed="is_attr_allowed",
        max_dim_x=2,
        max_dim_y=1,
        description="Centre of Gravity [x,y]",
    )
    @DebugIt()
    def centre(self):
        if self._CoG is None:
            raise AttributeError("No valid centre of gravity has been collected")
        return self._CoG

    @attribute(
        label="XProfile",
        dtype=[float],
        fisallowed="is_attr_allowed",
        max_dim_x=2000,
        max_dim_y=1,
        description="X Profile",
    )
    @DebugIt()
    def xprofile(self):
        if self._yprofile is None:
            raise AttributeError("No valid x profile has been collected")
        return self._xprofile

    @attribute(
        label="YProfile",
        dtype=[float],
        fisallowed="is_attr_allowed",
        max_dim_x=2000,
        max_dim_y=1,
        description="Y Profile",
    )
    @DebugIt()
    def yprofile(self):
        if self._yprofile is None:
            raise AttributeError("No valid y profile has been collected")
        return self._yprofile

    @attribute(
        label="XFit",
        dtype=[float],
        fisallowed="is_attr_allowed",
        max_dim_x=20,
        max_dim_y=1,
        description="X fit gaussian parameters",
    )
    @DebugIt()
    def xfit(self):
        if self._xfit is None:
            raise AttributeError("No valid x fit has been collected")
        return self._xfit

    @attribute(
        label="YFit",
        dtype=[float],
        fisallowed="is_attr_allowed",
        max_dim_x=20,
        max_dim_y=1,
        description="Y Fit gaussian parameters",
    )
    @DebugIt()
    def yfit(self):
        if self._yfit is None:
            raise AttributeError("No valid y fit has been collected")
        return self._yfit

    @attribute(
        label="Image8",
        dtype=[["byte"]],
        fisallowed="is_attr_allowed",
        max_dim_x=10000,
        max_dim_y=10000,
        description="",
    )
    @DebugIt()
    def readImage8(self):
        if self._imageData is None:
            raise AttributeError("No valid image collected")
        if self._imageData[0] != self.BPP8:
            raise AttributeError("This is not a 8 bit image")
        return self._imageData[1]

    @attribute(
        label="Image16",
        dtype=[["uint16"]],
        fisallowed="is_attr_allowed",
        max_dim_x=2000,
        max_dim_y=2000,
        description="",
    )
    @DebugIt()
    def readImage16(self):
        if self._imageData is None:
            raise AttributeError("No valid image collected")
        if self._imageData[0] != self.BPP16:
            raise AttributeError("This is not a 16 bit image")
        return self._imageData[1]

    @attribute(
        label="Image32",
        dtype=[["uint32"]],
        fisallowed="is_attr_allowed",
        max_dim_x=2000,
        max_dim_y=2000,
        description="",
    )
    @DebugIt()
    def readImage32(self):
        if self._imageData is None:
            raise AttributeError("No valid image collected")
        if self._imageData[0] != self.BPP32:
            raise AttributeError("This is not a 16 bit image")
        return self._imageData[1]

    @DebugIt()
    def is_attr_allowed(self, attr):
        """ Allow reading but not writing of attributes whilst running
        """
        if attr == tango.AttReqType.READ_REQ:
            return self.get_state() not in [
                tango.DevState.UNKNOWN,
                tango.DevState.FAULT,
            ]
        else:
            return self.get_state() not in [
                tango.DevState.UNKNOWN,
                tango.DevState.FAULT,
                tango.DevState.RUNNING,
            ]

    @DebugIt()
    def is_attr_rw_allowed(self, attr):
        """ Prohibit reading & writing of attributes whilst running
        """
        if attr == tango.AttReqType.READ_REQ:
            return self.get_state() not in [
                tango.DevState.UNKNOWN,
                tango.DevState.FAULT,
                tango.DevState.RUNNING,
            ]
        else:
            return self.get_state() not in [
                tango.DevState.UNKNOWN,
                tango.DevState.FAULT,
                tango.DevState.RUNNING,
            ]

    def bpmCallback(self, cog, xprofile, yprofile, xfit, yfit, imageData):
        if cog is not None:
            if (
                self._CoG is None
                or int(self._CoG[0]) != int(cog[0])
                or int(self._CoG[1]) != int(cog[1])
            ):
                log_debug(self, "bpmCallback(): pushing COG %s", cog)
                self.push_change_event("Centre", cog)
                with self._lock:
                    self._CoG = cog
            else:
                log_debug(self, "bpmCallback(): CoG is the same %s", cog)
        if xprofile is not None:
            xp = [float(p) for p in xprofile]
            self.push_change_event("XProfile", xp)
            with self._lock:
                self._xprofile = xp
        if yprofile is not None:
            yp = [float(p) for p in yprofile]
            self.push_change_event("YProfile", yp)
            with self._lock:
                self._yprofile = yp
        if xfit is not None:
            self.push_change_event("Xfit", xfit)
            with self._lock:
                self._xfit = xfit
        if yfit is not None:
            self.push_change_event("Yfit", yfit)
            with self._lock:
                self._yfit = yfit
        if imageData is not None:
            depth = imageData[0]
            image = imageData[1]
            if depth == self.BPP32:
                self.push_change_event("ReadImage32", image)
            elif depth == self.BPP16:
                self.push_change_event("ReadImage16", image)
            else:
                self.push_change_event("ReadImage8", image)
            with self._lock:
                self._imageData = imageData

    # -------------------------------------------------------------------------
    # commands
    # -------------------------------------------------------------------------
    @command
    @DebugIt()
    def Reset(self):
        """ Reset will force a stop, reload the last saved configuration.
        """
        self._nanoBpm.deviceReset()

    @command(
        dtype_out=(str,),
        doc_out="Get the hardware and software configuration of the device",
    )
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def GetDeviceInfo(self):
        """ Get the hardware and software configuration of the device.
        """
        deviceInfo = self._nanoBpm.getDeviceInfo()
        return ["{0}={1}".format(key, value) for key, value in deviceInfo.items()]

    @command(dtype_out=(str,), doc_out="Get the current device configuration")
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def GetDeviceConfig(self):
        """ Get the current device configuration.
        """
        deviceConfig = self._nanoBpm.getDeviceConfig()
        return ["{0}={1}".format(key, value) for key, value in deviceConfig.items()]

    @command(dtype_out=(str,), doc_out="Get the current device parameters")
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def GetDeviceParameters(self):
        """ Get the current device parameters.
        """
        deviceParameters = self._nanoBpm.getDeviceParameters()
        return ["{0}={1}".format(key, value) for key, value in deviceParameters.items()]

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def CollectDark(self):
        """ Collect and store a dark current image.
        """
        self.set_state(tango.DevState.RUNNING)
        gevent.spawn(self._doCollectDark)

    def _doCollectDark(self):
        log_info(self, "CollectDark(): Starting dark current image collection")
        self._nanoBpm.storeDark = True
        self._nanoBpm.readAve16Sum32()
        self._nanoBpm.storeDark = False
        log_info(self, "CollectDark(): Dark current image collection complete")
        with self._lock:
            if self._imageData is not None:
                self.set_state(tango.DevState.ON)
            else:
                self.set_state(tango.DevState.FAULT)

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def Collect(self):
        self.set_state(tango.DevState.RUNNING)
        gevent.spawn(self._doCollect)

    def _doCollect(self):
        if self._imageDepth == self.BPP32:
            log_info(self, "Collect(): collecting Ave16/sum32 image")
            self._nanoBpm.readAve16Sum32()
        elif self._imageDepth == self.BPP16:
            log_info(self, "Collect(): collecting 16 bit image")
            self._nanoBpm.readImage16()
        else:
            log_info(self, "Collect(): collecting 8 bit image")
            self._nanoBpm.readImage8()
        log_info(self, "Collect(): collection complete")

        with self._lock:
            if self._imageData is not None:
                self.set_state(tango.DevState.ON)
            else:
                self.set_state(tango.DevState.FAULT)

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def Start(self):
        self.set_state(tango.DevState.RUNNING)
        if self._acqMode == self.CONTINUOUS:
            self._nanoBpm.startContinuousFrame()
        else:
            self._nanoBpm.startDataStreaming()

    @command
    @DebugIt()
    def Stop(self):
        if self._acqMode == self.CONTINUOUS:
            self._nanoBpm.stopContinuousFrame()
        else:
            self._nanoBpm.stopDataStreaming()

        self.set_state(tango.DevState.ON)

    @DebugIt()
    def is_command_allowed(self):
        return self.get_state() not in [
            tango.DevState.UNKNOWN,
            tango.DevState.FAULT,
            tango.DevState.RUNNING,
        ]


# -------------------------------------------------------------------------
# Run server
# -------------------------------------------------------------------------
def main():
    from tango import GreenMode
    from tango.server import run

    run([NanoBpm], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
