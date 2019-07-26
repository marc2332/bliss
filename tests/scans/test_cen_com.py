# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import numpy
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning import scan, chain
from bliss.scanning.acquisition import timer, calc, motor, counter
from bliss.common import event
from bliss.common.standard import plotselect


def test_pkcom_ascan_gauss(session):

    roby = getattr(setup_globals, "roby")
    m1 = getattr(setup_globals, "m1")
    diode = getattr(setup_globals, "diode")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.ascan(roby, 0, 10, 10, 0, simul_counter, save=False, return_scan=True)

    p = s.peak(simul_counter)
    fwhm = s.fwhm(simul_counter)
    c = s.com(simul_counter)

    assert pytest.approx(p, 5)
    assert pytest.approx(fwhm, 2.3548)  # std dev is 1
    assert pytest.approx(c, 5)
    assert pytest.raises(ValueError, "s.peak(simul_counter, m1)")
    assert pytest.raises(KeyError, "s.peak(diode)")

    s.goto_peak(simul_counter)
    assert pytest.approx(roby.position, p)
    s.goto_com(simul_counter)
    assert pytest.approx(roby.position, c)

    # m1.move(1)
    # scans.lineup(m1, -2, 2, 20, 0, simul_counter, save=False)
    # assert pytest.approx(m1, 0)
    # counter.close()


def test_pkcom_a2scan_gauss(session):

    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.a2scan(
        roby, 0, 10, robz, 0, 5, 10, 0, simul_counter, save=False, return_scan=True
    )

    assert pytest.raises(ValueError, "s.peak(simul_counter)")

    p = s.peak(simul_counter, roby)
    assert pytest.approx(p, 5)


def test_pkcom_timescan_gauss(session):

    center = 0.1 * 10 / 2
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.timescan(0.1, simul_counter, npoints=10, save=False, return_scan=True)

    p = s.peak(simul_counter)
    assert pytest.approx(p, center)


def test_plotselect1(session):
    mg = session.env_dict["ACTIVE_MG"]  # counts diode2 and diode3
    roby = getattr(setup_globals, "roby")

    simul_counter1 = getattr(setup_globals, "diode2")
    simul_counter2 = getattr(setup_globals, "diode3")
    simul_counter4 = getattr(setup_globals, "diode4")

    # Select counter via library function
    scans.plotselect(simul_counter1)
    s = scans.ascan(roby, 0, .1, 5, 0, mg, simul_counter4, save=False)

    # _get_selected_counter_name() is valid only after a scan.
    assert simul_counter1.fullname == scans._get_selected_counter_name()

    # Select counter via user function
    plotselect(simul_counter2)
    assert simul_counter2.fullname == scans._get_selected_counter_name()

    plotselect(simul_counter4)
    assert simul_counter4.fullname == scans._get_selected_counter_name()


def test_plotselect_and_global_cen(session):
    roby = getattr(setup_globals, "roby")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    scans.plotselect(simul_counter)
    s = scans.ascan(roby, 0, .1, 5, 0, simul_counter, save=False)
    assert simul_counter.fullname == scans._get_selected_counter_name()
    cen_pos = scans.cen()
    assert pytest.approx(0.05, abs=1e-3) == cen_pos[0]

    # just call goto_X to go through the code
    scans.goto_cen()
    scans.goto_com()
    scans.goto_peak()
