# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright (c) : 2015
# Beamline Control Unit, European Synchrotron Radiation Facility
# BP 220, Grenoble 38043
# FRANCE
#
# Distributed under the terms of the GNU Lesser General Public License,
# either version 3 of the License, or (at your option) any later version.
# See LICENSE.txt for more info.

"""CT2 (P201/C208) ESRF counter card

CT2 (P201/C208) ESRF counter card TANGO device
"""

__all__ = ["CT2", "main"]

import time

import gevent
from gevent import select

from bliss.common.event import connect
from bliss.config.static import get_config

from PyTango import Util, GreenMode
from PyTango import AttrQuality, AttrWriteType, DispLevel, DevState
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import class_property, device_property

from ...device import CT2Device, AcqMode, AcqStatus
from ...device import ErrorSignal, PointNbSignal, StatusSignal


def switch_state(tg_dev, state=None, status=None):
    """Helper to switch state and/or status and send event"""
    if state is not None:
        tg_dev.set_state(state)
        tg_dev.push_change_event("state")
        if state in (DevState.ALARM, DevState.UNKNOWN, DevState.FAULT):
            msg = "State changed to " + str(state)
            if status is not None:
                msg += ": " + status
    if status is not None:
        tg_dev.set_status(status)
        tg_dev.push_change_event("status")


class CT2(Device):
    """
    CT2 (P201/C208) ESRF counter card TANGO device
    """
    __metaclass__ = DeviceMeta

    card_name = device_property(dtype='str', default_value="p201")
    def_acq_mode = device_property(dtype='str', default_value="IntTrigReadout")

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

    def init_device(self):
        Device.init_device(self)
        for attr in ("state", "status", "last_error", "last_point_nb",
                     "acq_status", "acq_mode", "acq_expo_time",
                     "acq_nb_points", "acq_channels"):
            self.set_change_event(attr, True, False)

        self.__last_error = ""
        self.__last_point_nb_info = -1, 0, AttrQuality.ATTR_VALID

        try:
            config = get_config()
            util = Util.instance()
            if util.is_svr_starting():
                acq_mode = AcqMode[self.def_acq_mode]
                self.device = CT2Device(config, self.card_name, acq_mode)
                connect(self.device, ErrorSignal, self.__on_error)
                connect(self.device, PointNbSignal, self.__on_point_nb)
                connect(self.device, StatusSignal, self.__on_status)
            else:
                self.apply_config()
            switch_state(self, DevState.ON, "Ready!")
        except Exception as e:
            msg = "Exception initializing device: {0}".format(e)
            self.error_stream(msg)
            switch_state(self, DevState.FAULT, msg)

    def delete_device(self):
        self.device.event_loop.kill()

    @attribute(dtype='str', label="Last error")
    def last_error(self):
        return self.__last_error

    @attribute(dtype='int32', label="Last point nb.")
    def last_point_nb(self):
        return self.__last_point_nb_info

    @attribute(dtype='str', label="Acq. mode",
               memorized=True, hw_memorized=True,
               doc="Acquisition mode (supported: 'IntTrigReadout', " \
                                                "'SoftTrigReadout', " \
                                                "'IntTrigMulti')")
    def acq_mode(self):
        return self.device.acq_mode.name

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self.device.acq_mode = AcqMode[acq_mode]
        self.push_change_event("acq_mode", acq_mode)

    @attribute(dtype='str', label="Acq. status",
               doc="Acquisition status")
    def acq_status(self):
        return self.device.acq_status.name

    @attribute(dtype='float64', label="Acq. expo. time", unit="s",
               standard_unit="s", display_unit="s", format="%6.3f",
               memorized=True, hw_memorized=True,
               doc="Acquisition exposition time (s)")
    def acq_expo_time(self):
        return self.device.acq_expo_time

    @acq_expo_time.setter
    def acq_expo_time(self, acq_expo_time):
        self.device.acq_expo_time = acq_expo_time
        self.push_change_event("acq_expo_time", acq_expo_time)

    @attribute(dtype='uint32', label="Acq. nb. points",
               memorized=True, hw_memorized=True,
               doc="Number of points per acquisition ")
    def acq_nb_points(self):
        return self.device.acq_nb_points

    @acq_nb_points.setter
    def acq_nb_points(self, acq_nb_points):
        self.device.acq_nb_points = acq_nb_points
        self.push_change_event("acq_nb_points", acq_nb_points)

    @attribute(dtype=('int16',), max_dim_x=12, label="Active channels",
               doc="List of active channels (first is 1)")
    def acq_channels(self):
        return tuple(self.device.acq_channels)

    @acq_channels.setter
    def acq_channels(self, acq_channels):
        self.device.acq_channels = acq_channels
        self.push_change_event("acq_channels", acq_channels)

    @attribute(dtype='float64', label="Timer clock freq.", unit="Hz",
               standard_unit="Hz", display_unit="Hz", format="%10.3g",
               memorized=True, hw_memorized=True,
               doc="Timer clock frequency (Hz)")
    def timer_freq(self):
        return self.device.timer_freq

    @timer_freq.setter
    def timer_freq(self, timer_freq):
        self.device.timer_freq = timer_freq
        self.push_change_event("timer_freq", timer_freq)

    @attribute(dtype=('uint32',), max_dim_x=12)
    def counters(self):
        return self.device.counters

    @attribute(dtype=('uint32',), max_dim_x=12)
    def latches(self):
        return self.device.latches

    @attribute(dtype=(('uint32',),), max_dim_x=65535, max_dim_y=65535)
    def data(self):
        return self.device.read_data()

    @command
    def apply_config(self):
        # first, empty FIFO
        self.device.read_data()
        # then, reload config and apply it to the device
        self.device.config.reload()
        self.device.apply_config()

    @command
    def reset(self):
        self.device.reset()

    @command(dtype_in=('uint16',),
             doc_in="list of counters to latch (first counter == 1)")
    def trigger_latch(self, counters):
        self.device.trigger_latch(counters)

    @command
    def prepare_acq(self):
        self.device.prepare_acq()

    @command
    def start_acq(self):
        self.device.start_acq()

    @command
    def stop_acq(self):
        self.device.stop_acq()

    @command
    def trigger_point(self):
        self.device.trigger_point()

    @property
    def card(self):
        return self.device.card

    def __set_last_point_nb(self, point_nb, timestamp=None, quality=None):
        if timestamp is None:
            timestamp = time.time()
        if quality is None:
            if self.device.acq_status == AcqStatus.Running:
                quality = AttrQuality.ATTR_CHANGING
            else:
                quality = AttrQuality.ATTR_VALID
        self.__last_point_nb = int(point_nb), timestamp, quality
        self.__last_point_nb_timestamp = timestamp
        self.push_change_event("last_point_nb", *self.__last_point_nb)

    def __set_last_error(self, error):
        self.__last_error = error
        self.push_change_event("last_error", error)

    def __on_error(self, error):
        self.__set_last_error(error)

    def __on_status(self, status):
        if status == AcqStatus.Ready:
            quality = AttrQuality.ATTR_VALID
            switch_state(self, DevState.ON, "Ready!")
        elif status == AcqStatus.Running:
            quality = AttrQuality.ATTR_CHANGING
            acq_mode = self.device.acq_mode.name
            switch_state(self, DevState.RUNNING,
                         "acquiring in {0} mode".format(acq_mode))            
        self.push_change_event("acq_status", status.name, time.time(), quality)

    def __on_point_nb(self, point_nb):
        self.__set_last_point_nb(point_nb)


def main(args=None, **kwargs):
    from PyTango.server import run
    kwargs['green_mode'] = kwargs.get('green_mode', GreenMode.Gevent)
    return run((CT2,), args=args, **kwargs)


if __name__ == '__main__':
    main()
