# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
import time
import numpy
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning import scan, chain
from bliss.scanning.acquisition import timer, calc, motor, counter
from bliss.common import event


def test_ascan(session):
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    m1 = getattr(setup_globals, "m1")
    counter = counter_class("gaussian", 10, cnt_time=0)
    s = scans.ascan(m1, 0, 10, 10, 0, counter, return_scan=True, save=False)
    assert m1.position() == 10
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["gaussian"], counter.data)


def test_ascan_gauss(session):
    counter_class = getattr(setup_globals, "AutoScanGaussianCounter")
    m1 = getattr(setup_globals, "m1")
    counter = counter_class("gaussianCurve")
    s = scans.ascan(m1, 0, 10, 10, 0, counter, return_scan=True, save=False)
    assert m1.position() == 10
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["gaussianCurve"], counter.data)
    counter.close()


def test_dscan(session):
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    counter = counter_class("gaussian", 10, cnt_time=0)
    m1 = getattr(setup_globals, "m1")
    # contrary to ascan, dscan returns to start pos
    start_pos = m1.position()
    s = scans.dscan(m1, -2, 2, 10, 0, counter, return_scan=True, save=False)
    assert m1.position() == start_pos
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["m1"], numpy.linspace(start_pos - 2, start_pos + 2, 10), atol=5e-4
    )
    assert numpy.array_equal(scan_data["gaussian"], counter.data)


def test_dscan_move_done(session):
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    counter = counter_class("gaussian", 10, cnt_time=0)
    m1 = getattr(setup_globals, "m1")

    # Callback
    positions = []

    def target(done):
        if done:
            positions.append(m1.dial())

    event.connect(m1, "move_done", target)

    # contrary to ascan, dscan returns to start pos
    start_pos = m1.position()
    s = scans.dscan(m1, -2, 2, 10, 0, counter, return_scan=True, save=False)
    assert m1.position() == start_pos
    scan_data = s.get_data()
    assert numpy.allclose(
        scan_data["m1"], numpy.linspace(start_pos - 2, start_pos + 2, 10), atol=5e-4
    )
    assert numpy.array_equal(scan_data["gaussian"], counter.data)
    assert positions[0] == -2
    assert positions[-2] == 2
    assert positions[-1] == 0

    event.disconnect(m1, "move_done", target)


def test_pointscan(session):
    m0 = getattr(setup_globals, "m0")
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    counter = counter_class("gaussian", 10, cnt_time=0)
    print counter.data
    points = [0.0, 1.0, 3.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0, 50.0]
    s = scans.pointscan(m0, points, 0, counter, return_scan=True, save=False)
    assert m0.position() == 50.0
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["m0"], points)
    assert numpy.array_equal(scan_data["gaussian"], counter.data)


def test_lookupscan(session):
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    diode = getattr(setup_globals, "diode")
    s = scans.lookupscan(0.1, roby, (0, 1), robz, (1, 2), diode, save=False)
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["roby"], (0, 1))
    assert numpy.array_equal(scan_data["robz"], (1, 2))


def test_anscan(session):
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    diode = getattr(setup_globals, "diode")
    s = scans.anscan(0.1, 2, roby, 0, 1, robz, 1, 2, diode, save=False)
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["roby"], (0, 1))
    assert numpy.array_equal(scan_data["robz"], (1, 2))


def test_all_anscan(session):
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    robz2 = getattr(setup_globals, "robz2")
    m0 = getattr(setup_globals, "m0")
    m1 = getattr(setup_globals, "m1")
    diode = getattr(setup_globals, "diode")
    # just call them to check syntax
    # real test is done else where
    scans.a5scan(
        roby,
        0,
        0.1,
        robz,
        0,
        0.1,
        robz2,
        0,
        0.1,
        m0,
        0,
        0.1,
        m1,
        0,
        0.1,
        2,
        0.1,
        diode,
        save=False,
    )
    scans.a4scan(
        roby, 0, 0.1, robz, 0, 0.1, robz2, 0, 0.1, m0, 0, 0.1, 2, 0.1, diode, save=False
    )
    scans.a3scan(roby, 0, 0.1, robz, 0, 0.1, robz2, 0, 0.1, 2, 0.1, diode, save=False)


def test_scan_callbacks(session):

    res = {"new": False, "end": False, "values": []}

    def on_scan_new(scan_info):
        res["new"] = True

    def on_scan_data(scan_info, values):
        res["values"].append(values[counter.name])

    def on_scan_end(scan_info):
        res["end"] = True

    event.connect(scan, "scan_new", on_scan_new)
    event.connect(scan, "scan_data", on_scan_data)
    event.connect(scan, "scan_end", on_scan_end)

    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan=True, save=False)
    assert res["new"]
    assert res["end"]
    assert numpy.array_equal(numpy.array(res["values"]), counter.data)


def test_calc_counters(session):
    m1 = getattr(setup_globals, "m1")
    c = chain.AcquisitionChain()
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    cnt = counter_class("gaussian", 10, cnt_time=0)
    t = timer.SoftwareTimerMaster(0, npoints=10)
    cnt_acq_device = counter.SamplingCounterAcquisitionDevice(cnt, count_time=0)
    c.add(t, cnt_acq_device)
    calc_cnt = calc.CalcAcquisitionDevice(
        "bla",
        (cnt_acq_device,),
        lambda y, x: {"pow": x["gaussian"] ** 2},
        (chain.AcquisitionChannel("pow", numpy.float, ()),),
    )
    c.add(t, calc_cnt)
    top_master = motor.LinearStepTriggerMaster(10, m1, 0, 1)
    c.add(top_master, t)

    s = scan.Scan(c, name="calc_scan", save=False)
    s.run()
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["gaussian"] ** 2, scan_data["pow"])


def test_calc_counter_callback(session):
    m1 = getattr(setup_globals, "m1")
    c = chain.AcquisitionChain()
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    cnt = counter_class("gaussian", 10, cnt_time=0)
    t = timer.SoftwareTimerMaster(0, npoints=10)
    cnt_acq_device = counter.SamplingCounterAcquisitionDevice(cnt, count_time=0)
    c.add(t, cnt_acq_device)

    class CBK(calc.CalcHook):
        def __init__(self):
            self.prepare_called = 0
            self.start_called = 0
            self.stop_called = 0

        def compute(self, sender, data_dict):
            return {"pow": data_dict["gaussian"] ** 2}

        def prepare(self):
            self.prepare_called += 1

        def start(self):
            self.start_called += 1

        def stop(self):
            self.stop_called += 1

    cbk = CBK()
    calc_cnt = calc.CalcAcquisitionDevice(
        "bla",
        (cnt_acq_device,),
        cbk,
        (chain.AcquisitionChannel("pow", numpy.float, ()),),
    )
    c.add(t, calc_cnt)
    top_master = motor.LinearStepTriggerMaster(10, m1, 0, 1)
    c.add(top_master, t)

    s = scan.Scan(c, name="calc_scan", save=False)
    s.run()
    assert cbk.prepare_called == 10
    assert cbk.start_called == 10
    assert cbk.stop_called == 1


def test_amesh(session):
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    counter = counter_class("gaussian", 15, cnt_time=0.01)
    s = scans.amesh(
        roby, 0, 10, 5, robz, 0, 5, 3, 0.01, counter, return_scan=True, save=False
    )
    assert roby.position() == 10
    assert robz.position() == 5
    scan_data = s.get_data()
    assert len(scan_data["roby"]) == 15
    assert len(scan_data["robz"]) == 15
    assert scan_data["roby"][0] == 0
    assert scan_data["roby"][4] == 10
    assert scan_data["roby"][-1] == 10
    assert scan_data["robz"][0] == 0
    assert scan_data["robz"][-1] == 5
    assert numpy.array_equal(scan_data["gaussian"], counter.data)


def test_dmesh(session):
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    counter = counter_class("gaussian", 15, cnt_time=0.01)
    start_roby = roby.position()
    start_robz = robz.position()
    s = scans.dmesh(
        roby, -5, 5, 5, robz, -3, 3, 3, 0.01, counter, return_scan=True, save=False
    )
    assert roby.position() == start_roby
    assert robz.position() == start_robz
    scan_data = s.get_data()
    assert len(scan_data["roby"]) == 15
    assert len(scan_data["robz"]) == 15
    assert scan_data["roby"][0] == start_roby - 5
    assert scan_data["roby"][-1] == start_roby + 5
    assert scan_data["robz"][0] == start_robz - 3
    assert scan_data["robz"][-1] == start_robz + 3
    assert numpy.array_equal(scan_data["gaussian"], counter.data)


def test_save_images(session, beacon, lima_simulator, scan_tmpdir):

    lima_sim = beacon.get("lima_simulator")
    roby = getattr(setup_globals, "roby")
    scan_saving = getattr(setup_globals, "SCAN_SAVING")
    saved_base_path = scan_saving.base_path
    try:
        scan_saving.base_path = str(scan_tmpdir)
        scan_saving.images_path_template = ""

        s = scans.ascan(roby, 0, 1, 2, 0.001, lima_sim, run=False)
        scan_path = s.writer.filename
        images_path = os.path.dirname(scan_path)
        image_filename = "lima_simulator_000%d.edf"

        s.run()

        assert os.path.isfile(scan_path)
        for i in range(2):
            assert os.path.isfile(os.path.join(images_path, image_filename % i))

        os.unlink(scan_path)
        os.unlink(os.path.join(images_path, image_filename % 0))

        s = scans.ascan(roby, 1, 0, 2, 0.001, lima_sim, save_images=False, run=False)

        s.run()

        scan_path = s.writer.filename
        assert os.path.isfile(scan_path)
        assert not os.path.isfile(
            os.path.join(scan_saving.base_path, image_filename % 0)
        )

        os.unlink(scan_path)

        s = scans.ascan(
            roby, 0, 1, 2, 0.001, lima_sim, save=False, save_images=True, run=False
        )

        s.run()

        scan_path = s.writer.filename
        assert not os.path.isfile(scan_path)
        assert not os.path.isfile(os.path.join(images_path, image_filename % 0))
    finally:
        scan_saving.base_path = saved_base_path
