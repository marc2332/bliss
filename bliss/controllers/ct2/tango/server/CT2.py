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

import PyTango
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import class_property, device_property
from PyTango import AttrQuality, AttrWriteType, DispLevel, DevState

import gevent
from gevent import select

from louie import dispatcher

from beacon.static import get_config

from ...device import CT2Device, AcqMode, ErrorSignal, PointNbSignal, StopSignal


def switch_state(tg_dev, state=None, status=None):
    """Helper to switch state and/or status and send event"""
    if state is not None:
        tg_dev.set_state(state)
        tg_dev.push_change_event("state")
        if state in (DevState.ALARM, DevState.UNKNOWN, DevState.FAULT):
            msg = "State changed to " + str(state)
            if status is not None:
                msg += ": " + status
            #logging.getLogger(tg_dev.get_name()).error(msg)
    if status is not None:
        tg_dev.set_status(status)
        tg_dev.push_change_event("status")


class CT2(Device):
    """
    CT2 (P201/C208) ESRF counter card TANGO device
    """
    __metaclass__ = DeviceMeta

    card_name = device_property(dtype='str', default_value="p201")
    

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

    def init_device(self):
        Device.init_device(self)
        for attr in ("state", "status", "last_error", "acq_mode",
                     "acq_expo_time", "acq_nb_points", "acq_channels"):
            self.set_change_event(attr, True, False)

        attr_map = self.get_device_attr()
        data_attr = attr_map.get_attr_by_name("data")
        data_attr.set_data_ready_event(True)

        self.__last_error = ""

        try:
            config = get_config()
            util = PyTango.Util.instance()
            if util.is_svr_starting():
                self.device = CT2Device(config, self.card_name)
                dispatcher.connect(self.__on_error, signal=ErrorSignal,
                                   sender=self.device)
                dispatcher.connect(self.__on_point_nb, signal=PointNbSignal,
                                   sender=self.device)
                dispatcher.connect(self.__on_stop, signal=StopSignal,
                                   sender=self.device)
            else:
                self.apply_config()

            self.__select_greenlet = gevent.spawn(self.device.run_forever)
            switch_state(self, DevState.ON, "Ready!")
        except Exception as e:
            msg = "Exception initializing device: {0}".format(e)
            self.error_stream(msg)
            switch_state(self, DevState.FAULT, msg)

    def delete_device(self):
        self.__select_greenlet.kill()

    @attribute(dtype='str', label="Last error")
    def last_error(self):
        return self.__last_error

    @attribute(dtype='str', label="Acq. mode",         
               memorized=True, hw_memorized=True,
               doc="Acquisition mode (supported: 'internal', )")
    def acq_mode(self):
        return self.device.acq_mode.name

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self.device.acq_mode = AcqMode[acq_mode]
        self.push_change_event("acq_mode", acq_mode)

    @attribute(dtype='float64', label="Acq. expo. time", unit="s",
               standard_unit="s", display_unit="s",
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

    @property
    def card(self):
        return self.device.card

    def __on_error(self, error):
        self.__last_error = error
        switch_state(self, state=DevState.FAULT, status=error)
        self.push_change_event("last_error", error)

    def __on_stop(self, *args):
        self.push_data_ready_event("data", -1)

    def __on_point_nb(self, point_nb):
        self.push_data_ready_event("data", point_nb)


def main(args=None, **kwargs):
    from PyTango.server import run
    kwargs['green_mode'] = kwargs.get('green_mode', PyTango.GreenMode.Gevent)
    return run((CT2,), args=args, **kwargs)


if __name__ == '__main__':
    main()
