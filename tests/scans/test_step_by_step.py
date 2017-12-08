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
from bliss.scanning import scan
from bliss.common import event


def test_ascan(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    m0 = getattr(setup_globals, 'm0')
    assert m0.position() == 0
    counter = counter_class("gaussian", 10, cnt_time=0)
    s = scans.ascan(m0, 0, 10, 10, 0, counter, return_scan=True, save=False)
    assert m0.position() == 10
    scan_data = scans.get_data(s)
    assert numpy.array_equal(scan_data['gaussian'], counter.data)


def test_dscan(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0)
    m0 = getattr(setup_globals, 'm0')
    s = scans.dscan(m0, 0, 2, 10, 0, counter, return_scan=True, save=False)
    assert m0.position() == 10
    scan_data = scans.get_data(s)
    assert numpy.array_equal(scan_data['gaussian'], counter.data)


def test_timescan(beacon):
    session = beacon.get("test_session")
    session.setup()
    counter_class = getattr(setup_globals, 'TestScanGaussianCounter')
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan=True, save=False)
    scan_data = scans.get_data(s)
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
