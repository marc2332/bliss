#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from tango import DevState
from tango.server import Device
from tango.server import attribute, command, device_property

from bliss.config.static import get_config


def switch_state(tg_dev, state=None, status=None):
    """Helper to switch state and/or status and send event"""
    if state is not None:
        tg_dev.set_state(state)
        #        tg_dev.push_change_event("state")
        if state in (DevState.ALARM, DevState.UNKNOWN, DevState.FAULT):
            msg = "State changed to " + str(state)
            if status is not None:
                msg += ": " + status
    if status is not None:
        tg_dev.set_status(status)


#        tg_dev.push_change_event("status")


class Multimeter(Device):

    name = device_property(dtype=str, doc="keithley bliss object name")

    def init_device(self):
        Device.init_device(self)

        try:
            config = get_config()
            self.device = config.get(self.name)
            switch_state(self, DevState.ON, "Ready!")
        except Exception as e:
            msg = "Exception initializing device: {0}".format(e)
            self.error_stream(msg)
            switch_state(self, DevState.FAULT, msg)

    def delete_device(self):
        if self.device:
            self.device.abort()

    @attribute(dtype=bool)
    def auto_range(self):
        return self.device.get_auto_range()

    @auto_range.setter
    def auto_range(self, auto_range):
        self.device.set_auto_range(auto_range)

    @attribute(dtype=float)
    def range(self):
        return self.get_range()

    @range.setter
    def range(self, range):
        self.set_range(range)

    @attribute(dtype=float)
    def nplc(self):
        return self.device.get_nplc()

    @nplc.setter
    def nplc(self, nplc):
        self.device.set_nplc(nplc)


def main():
    from tango import GreenMode
    from tango.server import run

    import logging

    fmt = "%(levelname)s %(asctime)-15s %(name)s: %(message)s"
    logging.basicConfig(format=fmt, level=logging.DEBUG)

    run([Multimeter], green_mode=GreenMode.Gevent)


if __name__ == "__main__":
    main()
