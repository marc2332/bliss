# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import random
import pytest
import gevent
import h5py
import numpy
import tango

from bliss.common.counter import SamplingCounter, SamplingMode, SoftCounter
from bliss.common.scans import loopscan, ct, ascan
from bliss.shell.cli.repl import ScanPrinter
from bliss import setup_globals
from bliss.common.soft_axis import SoftAxis

from bliss.controllers.counter import IntegratingCounterController
from bliss.controllers.simulation_diode import (
    SimulationDiodeSamplingCounter,
    SimulationDiodeIntegratingCounter,
    SimulationDiodeController,
)
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.scan import Scan
from bliss.scanning.acquisition.counter import (
    IntegratingCounterAcquisitionSlave,
    SamplingCounterAcquisitionSlave,
)
from bliss.scanning.acquisition.timer import SoftwareTimerMaster


class Diode(SamplingCounter):
    def __init__(self, diode, convert_func):
        super().__init__("test_diode", None, conversion_function=convert_func)
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

    def read_last(self):
        if self.more_than_once:
            return 2
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
        super.__init__("test_diode", diode.controller, conversion_function=convert_func)
        self.diode = diode


class DummyCounterController(IntegratingCounterController):
    def __init__(self):
        super().__init__("dummy_counter_controller")

    def get_values(self, from_index, *counters):
        gevent.sleep(0.01)
        return [10 * [random.randint(-100, 100)] for cnt in counters]


def test_diode(beacon):
    def multiply_by_two(x):
        test_diode.raw_value = x
        return 2 * x

    test_diode = SimulationDiodeSamplingCounter(
        "test_diode", SimulationDiodeController(), conversion_function=multiply_by_two
    )

    diode_value = test_diode.read()
    assert test_diode.raw_value * 2 == diode_value


def test_sampling_counter_mode(session):
    values = []

    def f(x):
        values.append(x)
        return x

    test_diode = SimulationDiodeSamplingCounter(
        "test_diode", SimulationDiodeController(), conversion_function=f
    )

    # USING DEFAULT MODE
    assert test_diode.mode.name == "MEAN"
    s = loopscan(1, 0.1, test_diode)
    # assert s.acq_chain.nodes_list[1].device.mode.name == "MEAN"
    assert s.get_data()["test_diode"] == pytest.approx(sum(values) / len(values))

    # UPDATING THE MODE
    values = []
    test_diode.mode = SamplingMode.INTEGRATE
    s = loopscan(1, 0.1, test_diode)
    assert s.get_data()["test_diode"] == pytest.approx(sum(values) * 0.1 / len(values))

    values = []
    test_diode.mode = "INTEGRATE"
    s = loopscan(1, 0.1, test_diode)
    assert s.get_data()["test_diode"] == pytest.approx(sum(values) * 0.1 / len(values))

    ## init as SamplingMode
    samp_cnt = SamplingCounter("test_diode", test_diode, mode=SamplingMode.INTEGRATE)
    assert samp_cnt.mode.name == "INTEGRATE"

    ## init as String
    samp_cnt = SamplingCounter("test_diode", test_diode, mode="INTEGRATE")
    assert samp_cnt.mode.name == "INTEGRATE"

    ## init as something else
    with pytest.raises(KeyError):
        samp_cnt = SamplingCounter("test_diode", test_diode, mode=17)

    ## two counters with different modes on the same acq_device
    diode2 = session.config.get("diode2")
    diode3 = session.config.get("diode3")
    diode3.mode = "INTEGRATE"

    s = loopscan(100, .001, diode2, diode3)

    d2 = numpy.sum(numpy.abs(s.get_data()["diode3"])) / .001
    d3 = numpy.sum(numpy.abs(s.get_data()["diode2"]))

    # use the fact that INTEGRATE is normalized by time
    assert 1. == pytest.approx(d2 / d2, rel=.25)


def test_SampCnt_mode_SAMPLES_from_conf(session):
    diode2 = session.config.get("diode2")
    diode9 = session.config.get("diode9")
    assert diode9.mode.name == "SAMPLES"

    s = loopscan(10, .05, diode2, diode9)

    assert (
        "simulation_diode_sampling_controller:diode2"
        in s.scan_info["acquisition_chain"]["timer"]["scalars"]
    )
    assert (
        "simulation_diode_sampling_controller:diode9"
        in s.scan_info["acquisition_chain"]["timer"]["scalars"]
    )
    assert (
        "simulation_diode_sampling_controller:diode9_samples"
        in s.scan_info["acquisition_chain"]["timer"]["spectra"]
    )


def test_SampCnt_mode_STATS(session, scan_tmpdir):
    # put scan file in a tmp directory
    session.scan_saving.base_path = str(scan_tmpdir)

    o = Timed_Diode()

    ax = SoftAxis("test-sample-pos", o)
    c_slow = SoftCounter(o, "read_slow", name="test-sample", mode=SamplingMode.STATS)
    s_slow = loopscan(1, .1, c_slow)

    data_slow = s_slow.get_data()
    assert all(data_slow["test-sample"] == numpy.array([17]))
    assert all(data_slow["test-sample_N"] == numpy.array([1]))
    assert all(numpy.isnan(data_slow["test-sample_std"]))

    c_fast = SoftCounter(o, "read_fast", name="test-stat", mode=SamplingMode.STATS)

    s_fast = ascan(ax, 1, 9, 8, .1, c_fast)

    data_fast = s_fast.get_data()

    assert all(
        data_fast["test-stat"] == numpy.array([1., 2., 3., 4., 5., 6., 7., 8., 9.])
    )
    assert all(
        data_fast["test-stat_std"] == numpy.array([0., 0., 0., 0., 0., 0., 0., 0., 0.])
    )
    assert all(
        data_fast["test-stat_var"] == numpy.array([0., 0., 0., 0., 0., 0., 0., 0., 0.])
    )
    assert all(
        data_fast["test-stat_p2v"] == numpy.array([0., 0., 0., 0., 0., 0., 0., 0., 0.])
    )
    assert all(
        data_fast["test-stat_min"] == numpy.array([1., 2., 3., 4., 5., 6., 7., 8., 9.])
    )
    assert all(
        data_fast["test-stat_max"] == numpy.array([1., 2., 3., 4., 5., 6., 7., 8., 9.])
    )


def test_SampCnt_STATS_algorithm():
    statistics = numpy.array([0, 0, 0, numpy.nan, numpy.nan])
    dat = numpy.random.normal(10, 1, 100)
    for k in dat:
        statistics = SamplingCounterAcquisitionSlave.rolling_stats_update(statistics, k)

    stats = SamplingCounterAcquisitionSlave.rolling_stats_finalize(statistics)

    assert pytest.approx(stats.mean, numpy.mean(dat))
    assert stats.N == len(dat)
    assert pytest.approx(stats.std, numpy.std(dat))
    assert pytest.approx(stats.var, numpy.var(dat))
    assert stats.min == numpy.min(dat)
    assert stats.max == numpy.max(dat)
    assert stats.p2v == numpy.max(dat) - numpy.min(dat)


def test_SampCnt_mode_SAMPLES(session, scan_tmpdir):
    # put scan file in a tmp directory
    session.scan_saving.base_path = str(scan_tmpdir)

    o = Timed_Diode()
    ax = SoftAxis("test-sample-pos", o)
    c_samp = SoftCounter(o, "read", name="test-samp", mode=SamplingMode.SAMPLES)
    s = ascan(ax, 1, 9, 8, .1, c_samp)

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


def test_SampCnt_mode_SINGLE(session, scan_tmpdir):
    env_dict = session.env_dict

    # put scan file in a tmp directory
    session.scan_saving.base_path = str(scan_tmpdir)

    diode2 = env_dict["diode2"]
    diode8 = env_dict["diode8"]
    assert diode8.mode == SamplingMode.SINGLE

    loops = loopscan(10, .1, diode2, diode8)
    diode2_dat = loops.get_data()["diode2"]
    diode8_dat = loops.get_data()["diode8"]

    # check that there is no averaging for diode10
    assert all(diode8_dat.astype(numpy.int) == diode8_dat)
    assert not all(diode2_dat.astype(numpy.int) == diode2_dat)


def test_SampCnt_mode_SINGLE_conv_func(session):
    env_dict = session.env_dict

    c = SoftCounter(
        value=lambda: 5,
        name="test",
        mode=SamplingMode.SINGLE,
        conversion_function=lambda n: 2 * n,
    )

    assert c.mode == SamplingMode.SINGLE

    s = loopscan(1, 0.01, c, save=False)

    assert s.get_data()[c] == 10


def test_SampCnt_mode_LAST(session):

    o = Timed_Diode()
    ax = SoftAxis("test-sample-pos", o)
    c = SoftCounter(o, "read_last", name="test", mode=SamplingMode.LAST)

    s = ascan(ax, 1, 9, 8, .1, c)

    assert all(s.get_data()["test"] == numpy.array([2, 2, 2, 2, 2, 2, 2, 2, 2]))


def test_SampCnt_statistics(session):
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")

    ct(.1, diode, diode2)
    statfields = (
        "mean",
        "N",
        "std",
        "var",
        "min",
        "max",
        "p2v",
        "count_time",
        "timestamp",
    )
    assert diode2.statistics._fields == statfields
    assert diode.statistics._fields == statfields
    assert diode2.statistics.N > 0
    assert diode2.statistics.std > 0


def test_SampCnt_mode_INTEGRATE_STATS(session):

    diode = session.config.get("diode")
    diode.mode = SamplingMode.INTEGRATE_STATS

    ct(.1, diode)
    statfields = (
        "mean",
        "N",
        "std",
        "var",
        "min",
        "max",
        "p2v",
        "count_time",
        "timestamp",
    )
    assert diode.statistics._fields == statfields
    assert diode.statistics._fields == statfields
    assert diode.statistics.N > 0
    assert diode.statistics.std > 0

    statistics = numpy.array([0, 0, 0, numpy.nan, numpy.nan])
    dat = numpy.random.normal(10, 1, 100)
    for k in dat:
        statistics = SamplingCounterAcquisitionSlave.rolling_stats_update(statistics, k)

    stats = SamplingCounterAcquisitionSlave.rolling_stats_finalize(statistics)

    count_time = .1
    integ_stats = SamplingCounterAcquisitionSlave.STATS_to_INTEGRATE_STATS(
        stats, count_time
    )

    new_dat = dat * count_time

    assert pytest.approx(integ_stats.mean, numpy.mean(new_dat))
    assert integ_stats.N == len(dat)
    assert pytest.approx(integ_stats.std, numpy.std(new_dat))
    assert pytest.approx(integ_stats.var, numpy.var(new_dat))
    assert integ_stats.min == numpy.min(new_dat)
    assert integ_stats.max == numpy.max(new_dat)
    assert pytest.approx(integ_stats.p2v, numpy.max(new_dat) - numpy.min(new_dat))


def test_integ_counter(beacon):
    acq_controller = DummyCounterController()

    def multiply_by_two(x):
        acq_controller.raw_value = x
        return 2 * x

    counter = SimulationDiodeIntegratingCounter(
        "test_diode", acq_controller, conversion_function=multiply_by_two
    )

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


def test_single_integ_counter(session):
    timer = SoftwareTimerMaster(0, npoints=1)
    acq_controller = DummyCounterController()
    counter = SimulationDiodeIntegratingCounter("test_diode", acq_controller)
    acq_device = IntegratingCounterAcquisitionSlave(counter, count_time=0)
    chain = AcquisitionChain()
    chain.add(timer, acq_device)
    s = Scan(chain, save=False)
    with gevent.Timeout(2):
        s.run()


def test_prepare_once_prepare_many(session):
    diode = session.config.get("diode")
    diode2 = session.config.get("diode2")
    diode3 = session.config.get("diode3")

    s = loopscan(10, .1, diode2, run=False)
    d = SamplingCounterAcquisitionSlave(diode, count_time=.1, npoints=10)
    s.acq_chain.add(s.acq_chain.nodes_list[0], d)
    s.run()
    dat = s.get_data()
    assert len(dat["diode2"]) == 10
    assert len(dat["diode"]) == 10

    # diode2 and diode3 are usually on the same SamplingCounterAcquisitionSlave
    # lets see if they can be split as well
    s = loopscan(10, .1, diode2, run=False)
    d = SamplingCounterAcquisitionSlave(diode3, count_time=.1, npoints=10)
    s.acq_chain.add(s.acq_chain.nodes_list[0], d)
    s.run()
    dat = s.get_data()
    assert len(dat["diode2"]) == 10
    assert len(dat["diode3"]) == 10


def test_tango_attr_counter(beacon, dummy_tango_server):
    counter = beacon.get("tg_dummy_counter")

    assert counter.read() == 1.4
    assert counter.unit == "mm"

    with pytest.raises(tango.DevFailed):
        wrong_counter = beacon.get("wrong_counter")

    # get BLISS counters
    tac_pos = beacon.get("tac_undu_position")
    tac_vel = beacon.get("tac_undu_velocity")

    # test "no unit"
    tac_acc = beacon.get("tac_undu_acceleration")

    with pytest.raises(tango.DevFailed):
        tac_cracoucas = beacon.get("tac_undu_cracoucas")

    # get UNDULATOR object
    u23a = beacon.get("u23a")

    assert u23a.position == 1.4
    assert u23a.position == tac_pos.read()

    assert u23a.velocity == tac_vel.read()
    assert u23a.acceleration == tac_acc.read()

    # Test missing uri
    with pytest.raises(KeyError):
        no_uri_counter = beacon.get("no_uri_counter")
