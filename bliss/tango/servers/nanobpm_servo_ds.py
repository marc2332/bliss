# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import sys
import logging
from functools import wraps

# tango imports
import tango
from tango import GreenMode
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property

import gevent
from gevent import event

__all__ = ["NanoBpmServo", "main"]


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


class NanoBpmServo(Device):

    # -------------------------------------------------------------------------
    # Device Properties
    # -------------------------------------------------------------------------
    NanoBPM = device_property(
        dtype=str,
        doc="Tango Device server for the Beam position monitor eg d26/nanobpm/1.",
    )
    XController = device_property(
        dtype=str, doc="Tango Device server for the x motor controller"
    )
    YController = device_property(
        dtype=str, doc="Tango Device server for the y motor controller"
    )

    # -------------------------------------------------------------------------
    # General methods
    # -------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        self._nanoBpmProxy = None
        self._xcontrolProxy = None
        self._ycontrolProxy = None
        self._centreId = None
        Device.__init__(self, *args, **kwargs)

    @DebugIt()
    def delete_device(self):
        if self._nanoBpmProxy is not None:
            if self._centreId is not None:
                self._nanoBpmProxy.unsubscribe_event(self._centreId)
        self._nanoBpm = None
        self._xcontrolProxy = None
        self._ycontrolProxy = None

    @DebugIt()
    def init_device(self):
        Device.init_device(self)
        self._logger = logging.getLogger(str(self))
        logging.basicConfig(level=logging.INFO)
        self._logger.setLevel(logging.DEBUG)
        try:
            self._nanoBpmProxy = tango.get_device_proxy(
                self.NanoBPM, green_mode=GreenMode.Gevent, wait=True, timeout=True
            )
            if self.XController is not None:
                self._xcontrolProxy = tango.DeviceProxy(self.XController)
            if self.YController is not None:
                self._ycontrolProxy = tango.DeviceProxy(self.YController)
            self._event = gevent.event.Event()
            self._servoId = None
            self._xcoord = 0
            self._ycoord = 0
            self._xmovePerPixel = 1.0
            self._ymovePerPixel = 1.0
            self._xcentre = 640
            self._ycentre = 512
            self._minimumXMove = 1.0
            self._minimumYMove = 1.0
            self._maximumXMove = 100.0
            self._maximumYMove = 100.0
            if self._nanoBpmProxy is not None:
                self._centreId = self._nanoBpmProxy.subscribe_event(
                    "Centre", tango.EventType.CHANGE_EVENT, self
                )
            self.set_state(tango.DevState.ON)
        except:
            self.set_state(tango.DevState.FAULT)

    @attribute(
        label="MinimumXMovement",
        dtype=float,
        memorized=True,
        unit="mm",
        description="Minimum X motor movement",
    )
    @DebugIt()
    def minimumXMovement(self):
        return self._minimumXMove

    @minimumXMovement.write
    @DebugIt()
    def minimumXMovement(self, minMove):
        self._minimumXMove = minMove

    @attribute(
        label="MinimumYMovement",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="mm",
        description="Minimum Y motor movement",
    )
    @DebugIt()
    def minimumYMovement(self):
        return self._minimumYMove

    @minimumYMovement.write
    @DebugIt()
    def minimumYMovement(self, minMove):
        self._minimumYMove = minMove

    @attribute(
        label="MaximumXMovement",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="mm",
        description="Maximum X motor movement",
    )
    @DebugIt()
    def maximumXMovement(self):
        return self._maximumXMove

    @maximumXMovement.write
    @DebugIt()
    def maximumXMovement(self, minMove):
        self._maximumXMove = minMove

    @attribute(
        label="MaximumYMovement",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="mm",
        description="Maximum Y motor movement",
    )
    @DebugIt()
    def maximumYMovement(self):
        return self._maximumYMove

    @maximumYMovement.write
    @DebugIt()
    def maximumYMovement(self, minMove):
        self._maximumYMove = minMove

    @attribute(
        label="XMovePerPixel",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="mm/pixel",
        description="Motor movement per bpm pixel",
    )
    @DebugIt()
    def xmovePerPixel(self):
        return self._xmovePerPixel

    @xmovePerPixel.write
    @DebugIt()
    def xmovePerPixel(self, movePerPixel):
        self._xmovePerPixel = movePerPixel

    @attribute(
        label="YMovePerPixel",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="mm/pixel",
        description="Motor movement per bpm pixel",
    )
    @DebugIt()
    def ymovePerPixel(self):
        return self._ymovePerPixel

    @ymovePerPixel.write
    @DebugIt()
    def ymovePerPixel(self, movePerPixel):
        self._ymovePerPixel = movePerPixel

    @attribute(
        label="XCentre",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="pixel",
        description="Nominal Y centre position",
    )
    @DebugIt()
    def xcentre(self):
        return self._xcentre

    @xcentre.write
    @DebugIt()
    def xcentre(self, centre):
        self._xcentre = centre

    @attribute(
        label="YCentre",
        dtype=float,
        memorized=True,
        hw_memorized=True,
        unit="pixel",
        description="Nominal Y centre position",
    )
    @DebugIt()
    def ycentre(self):
        return self._ycentre

    @ycentre.write
    @DebugIt()
    def ycentre(self, centre):
        self._ycentre = centre

    @command
    @DebugIt()
    @is_cmd_allowed("is_command_allowed")
    def StartServo(self):
        self.set_state(tango.DevState.RUNNING)
        self._servoId = gevent.spawn(self._doServo)

    def _doServo(self):
        while 1:
            self._logger.debug("Entering event wait")
            self._event.wait()
            self._event.clear()
            if self._xcoord != 0.0:
                incx = (self._xcentre - self._xcoord) * self._xmovePerPixel
                if abs(incx) > self._minimumXMove and abs(incx) < self._maximumXMove:
                    self._logger.debug(
                        "Need to move X by {0} minX {1}, maxX {2}".format(
                            incx, self._minimumXMove, self._maximumXMove
                        )
                    )
                    if self._xcontrolProxy is not None:
                        xpos = self._xcontrolProxy.read_attribute("position").value
                        self._xcontrolProxy.write_attribute("position", xpos + incx)
            if self._ycoord != 0.0:
                incy = (self._ycentre - self._ycoord) * self._ymovePerPixel
                if abs(incy) > self._minimumYMove and abs(incy) < self._maximumYMove:
                    self._logger.debug(
                        "Need to move Y by {0} minY {1}, maxY {2}".format(
                            incy, self._minimumYMove, self._maximumYMove
                        )
                    )
                    if self._ycontrolProxy is not None:
                        ypos = self._ycontrolProxy.read_attribute("position").value
                        self._logger.debug(
                            "current position is {0} should move to {1}".format(
                                ypos, ypos + incy
                            )
                        )
                        self._ycontrolProxy.write_attribute("position", ypos + incy)

    @command
    @DebugIt()
    def StopServo(self):
        self._servoId.kill()
        gevent.joinall([self._servoId])
        self._servoId = None
        self.set_state(tango.DevState.ON)

    @DebugIt()
    def is_command_allowed(self):
        return self.get_state() not in [
            tango.DevState.UNKNOWN,
            tango.DevState.FAULT,
            tango.DevState.RUNNING,
        ]

    def push_event(self, ev):
        if ev is not None:
            if ev.attr_value is not None and ev.attr_value.name == "centre":
                self._xcoord = ev.attr_value.value[0]
                self._ycoord = ev.attr_value.value[1]
                self._logger.debug(
                    "Bpm centre [{0},{1}]".format(self._xcoord, self._ycoord)
                )
                self._event.set()


# -------------------------------------------------------------------------
# Run server
# -------------------------------------------------------------------------
def main():
    from tango import GreenMode
    from tango.server import run

    run([NanoBpmServo], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
