# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import setup_globals
from bliss.common import scans
import numpy


def test_timescan(session):
    # test with sampling counter defined in setup file
    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    counter = counter_class("gaussian", 10, cnt_time=0.1)
    s = scans.timescan(0.1, counter, npoints=10, return_scan=True, save=False)
    scan_data = s.get_data()
    assert numpy.array_equal(scan_data["gaussian"], counter.data)


def test_ct(beacon):
    # test with integrating counter defined in yaml config
    integ_diode = beacon.get("integ_diode")
    assert scans.ct(0.1, integ_diode)
