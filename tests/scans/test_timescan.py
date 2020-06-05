# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.timer import SoftwareTimerMaster


def test_timescan(session):
    names = "sim_ct_gauss", "diode2", "diode9", "thermo_sample"
    detectors = [getattr(setup_globals, name) for name in names]
    s = scans.timescan(0.1, *detectors, npoints=10, return_scan=True, save=False)
    scan_data = s.get_data()
    for name in names:
        assert scan_data[name].size == 10
    assert numpy.array_equal(scan_data[names[0]], detectors[0].data)


def test_ct(session):
    # test with integrating counter defined in yaml config
    integ_diode = session.config.get("integ_diode")
    assert scans.ct(0.1, integ_diode)


def test_ct_bar(session):
    # Test bar ct
    s = scans.ct()
    # bar ct uses 1 second integration
    assert s.scan_info["count_time"] == pytest.approx(1.0)


def test_ct_count(session):
    # Test ct with a single argument
    s = scans.ct(2.0)
    # the first argument is used for the integration
    assert s.scan_info["count_time"] == pytest.approx(2.0)


def test_long_trigger_timescan(session, diode_acq_device_factory):
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(
        count_time=0.1, npoints=3, trigger_delay=1
    )
    master = SoftwareTimerMaster(0.1, name="timer", npoints=3)
    chain.add(master, acquisition_device_1)

    # Run scan
    s = Scan(chain, save=False)
    s.run()

    data = s.get_data()

    assert len(data) == 3
    assert len(data["elapsed_time"]) == 3  # check data is present
