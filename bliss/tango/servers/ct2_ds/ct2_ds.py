# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""CT2 (P201/C208) ESRF counter card

CT2 (P201/C208) ESRF counter card TANGO device
"""
from __future__ import absolute_import

__all__ = ["CT2", "main"]

import time
import logging
import warnings

import numpy

from PyTango import Util, GreenMode
from PyTango import AttrQuality, AttrWriteType, DispLevel, DevState
from PyTango.server import Device
from PyTango.server import attribute, command
from PyTango.server import class_property, device_property

from bliss.config.static import get_config
from bliss.controllers.ct2.card import BaseCard
from bliss.controllers.ct2.device import AcqMode, AcqStatus


def switch_state(tg_dev, state=None, status=None):
    """Helper to switch state and/or status and send event"""
    if state is not None:
        tg_dev.set_state(state)
        if state in (DevState.ALARM, DevState.UNKNOWN, DevState.FAULT):
            msg = "State changed to " + str(state)
            if status is not None:
                msg += ": " + status
    if status is not None:
        tg_dev.set_status(status)


def _to_enum(value, etype):
    if isinstance(value, (str, unicode)):
        return etype[value]
    return etype(value)


class CT2(Device):
    """
    CT2 (P201/C208) ESRF counter card TANGO device
    """

    card_name = device_property(dtype="str", default_value="p201")

    def __init__(self, *args, **kwargs):
        Device.__init__(self, *args, **kwargs)

    def init_device(self):
        Device.init_device(self)
        self.device = None

        try:
            config = get_config()
            util = Util.instance()
            if not util.is_svr_starting():
                config.reload()
            self.device = config.get(self.card_name)
            if isinstance(self.device, BaseCard):
                raise ValueError("ct2 card config is not supported anymore")

            switch_state(self, DevState.ON, "Ready!")
        except Exception as e:
            msg = "Exception initializing device: {0}".format(e)
            self.error_stream(msg)
            switch_state(self, DevState.FAULT, msg)

    def delete_device(self):
        if self.device:
            self.device.stop_acq()

    @attribute(dtype="str", label="Last error")
    def last_error(self):
        return self.device.last_error or ""

    @attribute(
        dtype="int32", label="Last point nb.", doc="Last acquisition point ready"
    )
    def last_point_nb(self):
        return self.device.last_point_nb

    @attribute(
        dtype="str",
        label="Acq. mode",
        memorized=True,
        hw_memorized=True,
        doc="Acquisition mode (supported: 'IntTrigReadout', "
        "'SoftTrigReadout', "
        "'IntTrigMulti')",
    )
    def acq_mode(self):
        return _to_enum(self.device.acq_mode, AcqMode).name

    @acq_mode.setter
    def acq_mode(self, acq_mode):
        self.device.acq_mode = AcqMode[acq_mode]

    @attribute(dtype="str", label="Acq. status", doc="Acquisition status")
    def acq_status(self):
        return _to_enum(self.device.acq_status, AcqStatus).name

    @attribute(
        dtype="float64",
        label="Acq. expo. time",
        unit="s",
        standard_unit="s",
        display_unit="s",
        format="%6.3f",
        memorized=True,
        hw_memorized=True,
        doc="Acquisition exposition time (s)",
    )
    def acq_expo_time(self):
        return self.device.acq_expo_time

    @acq_expo_time.setter
    def acq_expo_time(self, acq_expo_time):
        self.device.acq_expo_time = acq_expo_time

    @attribute(
        dtype="float64",
        label="Acq. expo. time",
        unit="s",
        standard_unit="s",
        display_unit="s",
        format="%6.3f",
        memorized=True,
        hw_memorized=True,
        doc="Acquisition point period (s)",
    )
    def acq_point_period(self):
        return self.device.acq_point_period

    @acq_point_period.setter
    def acq_point_period(self, acq_point_period):
        self.device.acq_point_period = acq_point_period

    @attribute(
        dtype="uint32",
        label="Acq. nb. points",
        memorized=True,
        hw_memorized=True,
        doc="Number of points per acquisition ",
    )
    def acq_nb_points(self):
        return self.device.acq_nb_points

    @acq_nb_points.setter
    def acq_nb_points(self, acq_nb_points):
        self.device.acq_nb_points = acq_nb_points

    @attribute(
        dtype=("int16",),
        max_dim_x=12,
        label="Active channels",
        doc="List of active channels (first is 1)",
    )
    def acq_channels(self):
        return tuple(self.device.acq_channels)

    @acq_channels.setter
    def acq_channels(self, acq_channels):
        self.device.acq_channels = acq_channels

    @attribute(
        dtype="float64",
        label="Timer clock freq.",
        unit="Hz",
        standard_unit="Hz",
        display_unit="Hz",
        format="%10.3g",
        memorized=True,
        hw_memorized=True,
        doc="Timer clock frequency (Hz)",
    )
    def timer_freq(self):
        return self.device.timer_freq

    @timer_freq.setter
    def timer_freq(self, timer_freq):
        self.device.timer_freq = timer_freq

    @attribute(dtype=("uint32",), max_dim_x=12)
    def counters(self):
        return self.device.counter_values

    @attribute(dtype=("uint32",), max_dim_x=12)
    def latches(self):
        return self.device.latches

    @attribute(dtype=(("uint32",),), max_dim_x=65535, max_dim_y=65535)
    def data(self):
        return self.device.read_data()

    @attribute(dtype=(int,), max_dim_x=12)
    def counters_status(self):
        status = self.device.get_counters_status()
        return [
            int(status[i]["enable"]) | (int(status[i]["run"]) << 1)
            for i in sorted(status)
        ]

    @command
    def reset(self):
        self.device.reset()

    @command(
        dtype_in=("uint16",), doc_in="list of counters to latch (first counter == 1)"
    )
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

    @command(dtype_out="DevVarCharArray")
    def dump_memory(self):
        data = self.device.dump_memory()
        return numpy.ndarray(shape=(len(data),), dtype=numpy.uint8, buffer=data)


def main(args=None, **kwargs):
    from PyTango.server import run

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(asctime)-15s %(name)s: %(message)s"
    )

    kwargs["green_mode"] = kwargs.get("green_mode", GreenMode.Gevent)
    return run((CT2,), args=args, **kwargs)


if __name__ == "__main__":
    main()
