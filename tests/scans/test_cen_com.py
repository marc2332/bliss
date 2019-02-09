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


def test_pkcom_ascan_gauss(session):

    counter_class = getattr(setup_globals, "AutoScanGaussianCounter")
    roby = getattr(setup_globals, "roby")
    m1 = getattr(setup_globals, "m1")
    diode = getattr(setup_globals, "diode")
    counter = counter_class("gaussianCurve")

    s = scans.ascan(roby, 0, 10, 10, 0, counter, save=False, return_scan=True)

    p = s.peak(counter)
    fwhm = s.fwhm(counter)
    c = s.com(counter)

    assert pytest.approx(p, 5)
    assert pytest.approx(fwhm, 2.3548)  # std dev is 1
    assert pytest.approx(c, 5)
    assert pytest.raises(ValueError, "s.peak(counter, m1)")
    assert pytest.raises(KeyError, "s.peak(diode)")

    s.goto_peak(counter)
    assert pytest.approx(roby.position, p)
    s.goto_com(counter)
    assert pytest.approx(roby.position, c)

    # m1.move(1)
    # scans.lineup(m1, -2, 2, 20, 0, counter, save=False)
    # assert pytest.approx(m1, 0)
    counter.close()


def test_pkcom_a2scan_gauss(session):

    counter_class = getattr(setup_globals, "AutoScanGaussianCounter")
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    counter = counter_class("gaussianCurve")

    s = scans.a2scan(
        roby, 0, 10, robz, 0, 5, 10, 0, counter, save=False, return_scan=True
    )

    assert pytest.raises(ValueError, "s.peak(counter)")

    p = s.peak(counter, roby)
    assert pytest.approx(p, 5)
    counter.close()


def test_pkcom_timescan_gauss(session):

    counter_class = getattr(setup_globals, "TestScanGaussianCounter")
    center = 0.1 * 10 / 2
    counter = counter_class("gaussian", 10, center, 0.1, cnt_time=0.1)

    s = scans.timescan(0.1, counter, npoints=10, save=False, return_scan=True)

    p = s.peak(counter)
    assert pytest.approx(p, center)


def test_plotselect_and_global_cen(session):
    counter_class = getattr(setup_globals, "AutoScanGaussianCounter")
    roby = getattr(setup_globals, "roby")
    counter = counter_class("gaussian")
    scans.plotselect(counter)
    s = scans.ascan(roby, 0, .1, 5, 0, counter, save=False)
    counter.close()
    assert counter.name == scans._get_selected_counter_name()
    cen_pos = scans.cen()
    assert pytest.approx(0.05, abs=1e-3) == cen_pos[0]

    # just call goto_X to go through the code
    scans.goto_cen()
    scans.goto_com()
    scans.goto_peak()
