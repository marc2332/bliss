# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import numpy
import h5py
from bliss.common.measurement import (
    SamplingCounter,
    IntegratingCounter,
    SamplingMode,
    SoftCounter,
)
from bliss.common.scans import loopscan, ct, ascan
from bliss.shell.cli.repl import ScanPrinter
from bliss import setup_globals
from bliss.common.soft_axis import SoftAxis
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


class Timed_Diode:
    """To be used in ascan as SoftAxis and SoftCounter at the same time"""

    def __init__(self):
        self.val = 0
        self.i = 0
        self.more_than_once = False

    def read(self):
        gevent.sleep((self.val % 5 + 1) * 0.002)
        self.i += 1
        return self.i

    def read_slow(self):
        gevent.sleep(.2)
        return 17

    def read_fast(self):
        gevent.sleep((self.val % 5 + 1) * 0.002)
        return self.val

    def read_once(self):
        if self.more_than_once:
            raise RuntimeError
        else:
            self.more_than_once = True
            return 1

    @property
    def position(self):
        return self.val

    @position.setter
    def position(self, val):
        self.val = val
        self.i = 0
        self.more_than_once = False


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


def test_SampCnt_mode_SAMPLES_from_conf(beacon):
    diode2 = beacon.get("diode2")
    diode9 = beacon.get("diode9")
    assert diode9.mode.name == "SAMPLES"

    s = loopscan(10, .05, diode2, diode9)

    assert (
        "simulation_diode_controller:diode2"
        in s.scan_info["acquisition_chain"]["timer"]["scalars"]
    )
    assert (
        "simulation_diode_controller:diode9"
        in s.scan_info["acquisition_chain"]["timer"]["scalars"]
    )
    assert (
        "simulation_diode_controller:diode9_samples"
        in s.scan_info["acquisition_chain"]["timer"]["spectra"]
    )


def test_SampCnt_mode_STATISTICS(session, scan_tmpdir):
    env_dict = session.env_dict

    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    o = Timed_Diode()

    ax = SoftAxis("test-sample-pos", o)
    c_slow = SoftCounter(
        o, "read_slow", name="test-sample", mode=SamplingMode.STATISTICS
    )
    s_slow = loopscan(1, .1, c_slow)

    data_slow = s_slow.get_data()
    assert all(data_slow["test-sample"] == numpy.array([17]))
    assert all(data_slow["test-sample_n"] == numpy.array([1]))
    assert all(numpy.isnan(data_slow["test-sample_std"]))

    c_fast = SoftCounter(o, "read_fast", name="test-stat", mode=SamplingMode.STATISTICS)

    s_fast = ascan(ax, 1, 9, 9, .1, c_fast)

    data_fast = s_fast.get_data()

    assert all(
        data_fast["test-stat"] == numpy.array([1., 2., 3., 4., 5., 6., 7., 8., 9.])
    )
    assert all(
        data_fast["test-stat_std"] == numpy.array([0., 0., 0., 0., 0., 0., 0., 0., 0.])
    )


def test_SampCnt_STATISTICS_algorithm():
    statistics = numpy.zeros(3)
    dat = numpy.random.normal(10, 1, 100)
    for k in dat:
        statistics = SamplingCounterAcquisitionDevice.welford_update(statistics, k)

    mean, count, std = SamplingCounterAcquisitionDevice.welford_finalize(statistics)

    assert pytest.approx(mean, numpy.mean(dat))
    assert count == len(dat)
    assert pytest.approx(std, numpy.std(dat))


def test_SampCnt_mode_SAMPLES(session, scan_tmpdir):
    env_dict = session.env_dict

    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    o = Timed_Diode()
    ax = SoftAxis("test-sample-pos", o)
    c_samp = SoftCounter(o, "read", name="test-samp", mode=SamplingMode.SAMPLES)
    s = ascan(ax, 1, 9, 9, .1, c_samp)

    assert (
        "Timed_Diode:test-samp" in s.scan_info["acquisition_chain"]["axis"]["scalars"]
    )
    assert (
        "Timed_Diode:test-samp_samples"
        in s.scan_info["acquisition_chain"]["axis"]["spectra"]
    )

    f = h5py.File(s.writer.filename)
    samples_h5 = numpy.array(f["1_ascan/measurement/Timed_Diode:test-samp_samples"])

    assert samples_h5.shape[0] == 9
    assert len(samples_h5.shape) == 2

    redis_dat = s.get_data()["test-samp_samples"]
    assert redis_dat.shape[0] == 9
    assert len(redis_dat.shape) == 2

    assert all(numpy.isnan(redis_dat.flatten()) == numpy.isnan(samples_h5.flatten()))
    mask = numpy.logical_not(numpy.isnan(redis_dat.flatten()))
    assert all((redis_dat.flatten() == samples_h5.flatten())[mask])


def test_SampCnt_mode_SINGLE_COUNT(session, scan_tmpdir):

    env_dict = session.env_dict
    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    diode2 = env_dict["diode2"]
    diode8 = env_dict["diode8"]
    assert diode8.mode == SamplingMode.SINGLE_COUNT

    with pytest.raises(RuntimeError):
        ct(.1, diode2, diode8)

    o = Timed_Diode()
    ax = SoftAxis("test-sample-pos", o)
    c = SoftCounter(o, "read_once", name="test", mode=SamplingMode.SINGLE_COUNT)
    s = ascan(ax, 1, 9, 9, .1, c)

    assert all(s.get_data()["test"] == numpy.ones(9))


def test_SampCnt_mode_FIRST_READ(session, scan_tmpdir):

    env_dict = session.env_dict
    # put scan file in a tmp directory
    env_dict["SCAN_SAVING"].base_path = str(scan_tmpdir)

    diode2 = env_dict["diode2"]
    diode10 = env_dict["diode10"]
    assert diode10.mode == SamplingMode.FIRST_READ

    loops = loopscan(10, .1, diode2, diode10)
    diode2_dat = loops.get_data()["diode2"]
    diode10_dat = loops.get_data()["diode10"]

    # check that there is no averaging for diode10
    assert all(diode10_dat.astype(numpy.int) == diode10_dat)
    assert not all(diode2_dat.astype(numpy.int) == diode2_dat)

    o = Timed_Diode()
    ax = SoftAxis("test-sample-pos", o)
    c = SoftCounter(o, "read_once", name="test", mode=SamplingMode.FIRST_READ)

    with pytest.raises(RuntimeError):
        s = ascan(ax, 1, 9, 9, .1, c)


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
