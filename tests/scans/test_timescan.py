# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.timer import SoftwareTimerMaster


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


def test_long_trigger_timescan(beacon, diode_acq_device_factory):
    chain = AcquisitionChain()
    acquisition_device_1 = diode_acq_device_factory.get(
        count_time=0.1, npoints=3, trigger_delay=1
    )
    master = SoftwareTimerMaster(0.1, name="timer", npoints=3)
    chain.add(master, acquisition_device_1)

    # Run scan
    s = Scan(chain, save=False)
    s.run()

    assert len(s.get_data()) == 3
    assert "elapsed_time" in s.get_data()
    assert len(s.get_data()["elapsed_time"]) == 3  # check data is present
