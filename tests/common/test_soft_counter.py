# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy.testing

from bliss.common.standard import loopscan
from bliss.common.measurement import SoftCounter


class NullObject(object):
    pass


class Object(object):
    @property
    def value(self):
        return 12.34

    @property
    def voltage(self):
        return 67.89

    def get_pressure(self):
        return 23.45


class Controller(object):
    def __init__(self, name):
        self.name = name


def test_soft_counter_read(beacon):

    null_no_name = NullObject()
    null_no_name.value = 45.67

    counter = SoftCounter(null_no_name)  # counter controller is None
    assert counter.read() == 45.67

    null_name = NullObject()
    null_name.name = "n1"
    null_name.value = 67.89

    counter = SoftCounter(null_name)
    assert counter.read() == 67.89

    o1 = Object()
    o1.name = "o1"

    counter = SoftCounter(o1)
    assert counter.read() == 12.34

    counter = SoftCounter(o1, value="voltage")
    assert counter.read() == 67.89

    counter = SoftCounter(o1, value="get_pressure")
    assert counter.read() == 23.45

    counter = SoftCounter(o1, value="get_pressure", apply=lambda v: v * 100 + 5.4)
    assert counter.read() == 23.45 * 100 + 5.4


def test_soft_counter_name(beacon):

    null_no_name = NullObject()
    null_no_name.value = 45.67

    ctrl = Controller("ctrl1")

    counter = SoftCounter(null_no_name)  # counter controller is None
    assert counter.name == "value"
    assert counter.fullname == "NullObject.value"

    counter = SoftCounter(null_no_name, name="current")
    assert counter.name == "current"
    assert counter.fullname == "NullObject.current"

    counter = SoftCounter(null_no_name, name="current", controller=ctrl)
    assert counter.name == "current"
    assert counter.fullname == "ctrl1.current"

    null_name = NullObject()
    null_name.name = "n1"
    null_name.value = 67.89

    counter = SoftCounter(null_name)
    assert counter.name == "value"
    assert counter.fullname == "n1.value"

    counter = SoftCounter(null_name, name="temp")
    assert counter.name == "temp"
    assert counter.fullname == "n1.temp"

    o1 = Object()
    o1.name = "o1"

    counter = SoftCounter(o1)
    assert counter.name == "value"
    assert counter.fullname == "o1.value"

    counter = SoftCounter(o1, name="humidity")
    assert counter.name == "humidity"
    assert counter.fullname == "o1.humidity"

    counter = SoftCounter(o1, value="voltage")
    assert counter.name == "voltage"
    assert counter.fullname == "o1.voltage"

    counter = SoftCounter(o1, value="voltage", name="position")
    assert counter.name == "position"
    assert counter.fullname == "o1.position"

    counter = SoftCounter(o1, value="get_pressure")
    assert counter.name == "get_pressure"
    assert counter.fullname == "o1.get_pressure"

    counter = SoftCounter(o1, value="get_pressure", name="pressure")
    assert counter.name == "pressure"
    assert counter.fullname == "o1.pressure"

    counter = SoftCounter(o1, value="get_pressure", name="pressure", controller=ctrl)
    assert counter.name == "pressure"
    assert counter.fullname == "ctrl1.pressure"


def test_soft_counter_scan(beacon):

    null_name = NullObject()
    null_name.name = "n1"
    null_name.value = 45.67

    o1 = Object()
    o1.name = "o1"

    c1 = SoftCounter(null_name)
    c2 = SoftCounter(o1, name="temp_deg")
    c3 = SoftCounter(o1, value="voltage")
    c4 = SoftCounter(o1, value="get_pressure")
    c5 = SoftCounter(o1, apply=lambda v: v * 9.0 / 5 + 32, name="temp_f")

    scan = loopscan(10, 0.01, c1, c2, c3, c4, c5, save=False)

    data = scan.get_data()

    # TODO: counter names should be full counter names after issue #395 is solved
    counter_names = {
        "elapsed_time",
        "value",
        "temp_deg",
        "voltage",
        "get_pressure",
        "temp_f",
    }
    assert set(data.keys()) == counter_names

    numpy.testing.assert_array_almost_equal(data["value"], 10 * [45.67])
    numpy.testing.assert_array_almost_equal(data["temp_deg"], 10 * [12.34])
    numpy.testing.assert_array_almost_equal(data["voltage"], 10 * [67.89])
    numpy.testing.assert_array_almost_equal(data["get_pressure"], 10 * [23.45])
    numpy.testing.assert_array_almost_equal(data["temp_f"], 10 * [12.34 * 9.0 / 5 + 32])
    return data


def test_sampling_counter_acquisition_device_mode(beacon):

    diode = beacon.get("diode")

    # USING DEFAULT MODE
    c = SoftCounter(diode, "read")
    assert c.acquisition_device_mode is None
    s = loopscan(10, 0.01, c, run=False)
    assert s.acq_chain.nodes_list[1].mode.name == "SIMPLE_AVERAGE"

    # UPDATING THE MODE
    c.acquisition_device_mode = "INTEGRATE"
    s = loopscan(10, 0.01, c, run=False)
    assert s.acq_chain.nodes_list[1].mode.name == "INTEGRATE"

    # SPECIFYING THE MODE
    c = SoftCounter(diode, "read", acquisition_device_mode="INTEGRATE")
    assert c.acquisition_device_mode == "INTEGRATE"
    s = loopscan(10, 0.01, c, run=False)
    assert s.acq_chain.nodes_list[1].mode.name == "INTEGRATE"
