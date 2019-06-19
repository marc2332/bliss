# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import numpy
from bliss.common.measurement import SamplingCounter, IntegratingCounter, SamplingMode
from bliss.common.scans import loopscan, ct
from bliss.shell.cli.repl import ScanPrinter
from bliss import setup_globals
from unittest import mock

from bliss.scanning.chain import AcquisitionChain, AcquisitionMaster
from bliss.scanning.scan import Scan
from bliss.scanning.acquisition.counter import (
    IntegratingCounterAcquisitionDevice,
    SamplingCounterAcquisitionDevice,
)
from bliss.scanning.acquisition.timer import SoftwareTimerMaster


class Diode(SamplingCounter):
    def __init__(self, diode, convert_func):
        SamplingCounter.__init__(
            self,
            "test_diode",
            None,
            grouped_read_handler=None,
            conversion_function=convert_func,
        )
        self.diode = diode

    def read(self, *args):
        self.last_read_value = self.diode.read()
        return self.last_read_value


class DiodeWithController(SamplingCounter):
    def __init__(self, diode, convert_func):
        SamplingCounter.__init__(
            self,
            "test_diode",
            diode.controller,
            grouped_read_handler=None,
            conversion_function=convert_func,
        )
        self.diode = diode


class AcquisitionController:
    pass


class IntegCounter(IntegratingCounter):
    def __init__(self, acq_controller, convert_func):
        IntegratingCounter.__init__(
            self,
            "test_integ_diode",
            None,
            acq_controller,
            grouped_read_handler=None,
            conversion_function=convert_func,
        )

    def get_values(self, from_index):
        return numpy.random.random(1)


def test_diode(beacon):
    diode = beacon.get("diode")

    def multiply_by_two(x):
        return 2 * x

    test_diode = Diode(diode, multiply_by_two)

    diode_value = test_diode.read()

    assert test_diode.last_read_value * 2 == diode_value


def test_diode_with_controller(beacon):
    diode = beacon.get("diode")

    def multiply_by_two(x):
        diode.raw_value = x
        return 2 * x

    test_diode = Diode(diode, multiply_by_two)

    diode_value = test_diode.read()

    assert diode.raw_value * 2 == diode_value


def test_sampling_counter_mode(beacon):
    diode = beacon.get("diode")
    values = []

    def f(x):
        values.append(x)
        return x

    test_diode = Diode(diode, f)

    # USING DEFAULT MODE
    assert test_diode.mode.name == "SIMPLE_AVERAGE"
    s = loopscan(1, 0.1, test_diode)
    assert s.acq_chain.nodes_list[1].device.mode.name == "SIMPLE_AVERAGE"
    assert s.get_data()["test_diode"] == pytest.approx(sum(values) / len(values))

    # UPDATING THE MODE
    values = []
    test_diode.mode = SamplingMode.INTEGRATE
    s = loopscan(1, 0.1, test_diode)
    assert s.acq_chain.nodes_list[1].device.mode.name == "INTEGRATE"
    assert s.get_data()["test_diode"] == pytest.approx(sum(values) * 0.1 / len(values))

    values = []
    test_diode.mode = "INTEGRATE"
    s = loopscan(1, 0.1, test_diode)
    assert s.acq_chain.nodes_list[1].device.mode.name == "INTEGRATE"
    assert s.get_data()["test_diode"] == pytest.approx(sum(values) * 0.1 / len(values))

    ## init as SamplingMode
    samp_cnt = SamplingCounter(diode, "test_diode", None, mode=SamplingMode.INTEGRATE)
    assert samp_cnt.mode.name == "INTEGRATE"

    ## init as String
    samp_cnt = SamplingCounter(diode, "test_diode", None, mode="INTEGRATE")
    assert samp_cnt.mode.name == "INTEGRATE"

    ## init as something else
    with pytest.raises(KeyError):
        samp_cnt = SamplingCounter(diode, "test_diode", None, mode=17)

    ## two counters with different modes on the same acq_device
    diode2 = beacon.get("diode2")
    diode3 = beacon.get("diode3")
    diode3.mode = "INTEGRATE"

    s = loopscan(30, .05, diode2, diode3)
    assert 1 == numpy.round(
        (
            numpy.sum(numpy.abs(s.get_data()["diode3"])) / .05
        )  # use the fact that INTEGRATE is normalized by time
        / numpy.sum(numpy.abs(s.get_data()["diode2"])),
        0,
    )


def test_integ_counter(beacon):
    acq_controller = AcquisitionController()

    def multiply_by_two(x):
        acq_controller.raw_value = x
        return 2 * x

    counter = IntegCounter(acq_controller, multiply_by_two)

    assert list(counter.get_values(0)) == list(2 * acq_controller.raw_value)


def test_bad_counters(session, beacon):
    sp = ScanPrinter()
    diode = session.env_dict["diode"]
    simu_mca = beacon.get("simu1")
    setup_globals.simu_mca = simu_mca
    try:
        simu_mca._bad_counters = True

        s = ct(0.1, diode)
    finally:
        simu_mca._bad_counters = False


def test_single_integ_counter(beacon):
    timer = SoftwareTimerMaster(0, npoints=1)
    acq_controller = AcquisitionController()
    acq_controller.name = "bla"
    counter = IntegCounter(acq_controller, None)
    acq_device = IntegratingCounterAcquisitionDevice(counter, 0, npoints=1)
    chain = AcquisitionChain()
    chain.add(timer, acq_device)
    s = Scan(chain, save=False)
    s.run()


def test_integ_start_once_true(beacon):
    acq_controller = AcquisitionController()
    acq_controller.name = "acq_controller"
    counter = IntegCounter(acq_controller, lambda x: x * 2)

    acq_device = IntegratingCounterAcquisitionDevice(
        counter, count_time=.1, npoints=1, start_once=True
    )
    master1 = SoftwareTimerMaster(0.1, npoints=1, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 1


def test_sampling_start_once_true(beacon):
    diode = beacon.get("diode")
    acq_device = SamplingCounterAcquisitionDevice(
        diode, count_time=.1, npoints=2, start_once=True
    )
    master1 = SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 2


def test_integ_start_once_false(beacon):
    acq_controller = AcquisitionController()
    acq_controller.name = "acq_controller"
    counter = IntegCounter(acq_controller, lambda x: x * 2)

    acq_device = IntegratingCounterAcquisitionDevice(
        counter, count_time=.1, npoints=1, start_once=False
    )
    master1 = SoftwareTimerMaster(0.1, npoints=1, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 1


def test_sampling_start_once_false(beacon):
    diode = beacon.get("diode")
    acq_device = SamplingCounterAcquisitionDevice(
        diode, count_time=.1, npoints=2, start_once=False
    )
    master1 = SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 2


def test_integ_prepare_once_true(beacon):
    acq_controller = AcquisitionController()
    acq_controller.name = "acq_controller"
    counter = IntegCounter(acq_controller, lambda x: x * 2)
    acq_device = IntegratingCounterAcquisitionDevice(
        counter, count_time=.1, npoints=1, prepare_once=True
    )
    master1 = SoftwareTimerMaster(0.1, npoints=1, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 1


def test_sampling_prepare_once_true(beacon):
    diode = beacon.get("diode")
    acq_device = SamplingCounterAcquisitionDevice(
        diode, count_time=.1, npoints=2, prepare_once=True
    )
    master1 = SoftwareTimerMaster(0.1, npoints=2, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 2


def test_integ_prepare_once_false(beacon):
    acq_controller = AcquisitionController()
    acq_controller.name = "acq_controller"
    counter = IntegCounter(acq_controller, lambda x: x * 2)
    acq_device = IntegratingCounterAcquisitionDevice(
        counter, count_time=.1, npoints=1, prepare_once=False
    )
    master1 = SoftwareTimerMaster(0.1, npoints=1, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 1


def test_sampling_prepare_once_false(beacon):
    diode = beacon.get("diode")
    acq_device = SamplingCounterAcquisitionDevice(
        diode, count_time=.1, npoints=1, prepare_once=False
    )
    master1 = SoftwareTimerMaster(0.1, npoints=1, name="timer1")
    ch = AcquisitionChain()
    ch.add(master1, acq_device)
    s = Scan(ch, name="bla")
    with gevent.Timeout(2):
        s.run()
    for k, v in s.get_data().items():
        assert len(v) == 1


def test_prepare_once_prepare_many(beacon):
    diode = beacon.get("diode")
    diode2 = beacon.get("diode2")
    diode3 = beacon.get("diode3")

    s = loopscan(10, .1, diode2, run=False)
    d = SamplingCounterAcquisitionDevice(diode, .1, npoints=10)
    s.acq_chain.add(s.acq_chain.nodes_list[0], d)
    s.run()
    dat = s.get_data()
    assert "diode2" in dat
    assert "diode" in dat
    assert len(s.get_data()["diode2"]) == 10
    assert len(s.get_data()["diode"]) == 10

    # diode2 and diode3 are usually on the same SamplingCounterAcquisitionDevice
    # lets see if they can be split as well
    s = loopscan(10, .1, diode2, run=False)
    d = SamplingCounterAcquisitionDevice(diode3, .1, npoints=10)
    s.acq_chain.add(s.acq_chain.nodes_list[0], d)
    s.run()
    dat = s.get_data()
    assert "diode2" in dat
    assert "diode3" in dat
    assert len(s.get_data()["diode2"]) == 10
    assert len(s.get_data()["diode3"]) == 10


def test_tango_attr_counter(beacon, dummy_tango_server):
    counter = beacon.get("tg_dummy_counter")

    assert counter.read() == 1.4
    assert counter.unit == "mm"
