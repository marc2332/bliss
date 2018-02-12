# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import numpy
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning import scan, chain
from bliss.scanning.acquisition import timer, calc, motor, counter
from bliss.common import event


def test_ascan(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    m1 = getattr(setup_globals, 'm1')
    counter = counter_class("gaussian", 10, cnt_time=0)
    s = scans.ascan(m1, 0, 10, 10, 0, counter, return_scan=True, save=False)
    assert m1.position() == 10
    scan_data = scans.get_data(s)
    assert numpy.array_equal(scan_data['gaussian'], counter.data)


def test_dscan(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0)
    m1 = getattr(setup_globals, 'm1')
    # contrary to ascan, dscan returns to start pos
    start_pos = m1.position()
    s = scans.dscan(m1, -2, 2, 10, 0, counter, return_scan=True, save=False)
    assert m1.position() == start_pos
    scan_data = scans.get_data(s)
    assert numpy.allclose(scan_data['m1'], numpy.linspace(start_pos-2, start_pos+2, 10), atol=5e-4)
    assert numpy.array_equal(scan_data['gaussian'], counter.data)


def test_timescan(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan=True, save=False)
    scan_data = scans.get_data(s)
    assert numpy.array_equal(scan_data['gaussian'], counter.data)


def test_pointscan(beacon):
    session = beacon.get("test_session")
    session.setup()
    m0 = getattr(setup_globals, 'm0')
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0)
    print counter.data
    points = [0.0, 1.0, 3.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0, 50.0]
    s = scans.pointscan(m0, points, 0, counter, return_scan=True, save=False)
    assert m0.position() == 50.0
    scan_data = scans.get_data(s)
    assert numpy.array_equal(scan_data['m0'], points)
    assert numpy.array_equal(scan_data['gaussian'], counter.data)

def test_scan_callbacks(beacon):
    session = beacon.get("test_session")
    session.setup()

    res = {"new": False, "end": False, "values": []}

    def on_scan_new(scan_info):
        res["new"] = True

    def on_scan_data(scan_info, values):
        res["values"].append(values[counter.name])

    def on_scan_end(scan_info):
        res["end"] = True

    event.connect(scan, 'scan_new', on_scan_new)
    event.connect(scan, 'scan_data', on_scan_data)
    event.connect(scan, 'scan_end', on_scan_end)

    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan=True, save=False)
    assert res["new"]
    assert res["end"]
    assert numpy.array_equal(numpy.array(res["values"]), counter.data)

def test_calc_counters(beacon):
    session = beacon.get("test_session")
    session.setup()
    m1 = getattr(setup_globals, 'm1')
    c = chain.AcquisitionChain()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    cnt = counter_class("gaussian", 10, cnt_time=0)
    t = timer.SoftwareTimerMaster(0, npoints=10)
    cnt_acq_device = counter.SamplingCounterAcquisitionDevice(cnt, count_time=0)
    c.add(t, cnt_acq_device)
    calc_cnt = calc.CalcAcquisitionDevice('bla',(cnt_acq_device,),
                                          lambda y,x: {'pow':x['gaussian']**2},
                                          (chain.AcquisitionChannel('pow',numpy.float,()),))
    c.add(t, calc_cnt)
    top_master = motor.LinearStepTriggerMaster(10,m1,0,1)
    c.add(top_master,t)

    s = scan.Scan(c, name='calc_scan',)
    s.run()
    scan_data = scans.get_data(s)
    assert numpy.array_equal(scan_data['gaussian']**2,scan_data['pow'])
