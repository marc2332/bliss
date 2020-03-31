# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning import scan, chain
from bliss.scanning.acquisition import timer, calc, motor, counter
from bliss.common import event
from bliss.shell.standard import plotselect, plotinit, cen, com, peak
from bliss.scanning.scan import ScanDisplay
from bliss.scanning import scan_tools
from bliss.common import plot


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
    with pytest.raises(ValueError):
        s.peak(simul_counter, m1)
    with pytest.raises(KeyError):
        s.peak(diode)

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
    plot.plotselect(simul_counter1)
    s = scans.ascan(roby, 0, .1, 5, 0, mg, simul_counter4, save=False)

    # _get_selected_counter_name() is valid only after a scan.
    assert simul_counter1.fullname == scan_tools.get_selected_counter_name()

    # Select counter via user function
    plotselect(simul_counter2)
    assert simul_counter2.fullname == scan_tools.get_selected_counter_name()

    plotselect(simul_counter4)
    assert simul_counter4.fullname == scan_tools.get_selected_counter_name()


def test_plotselect_axis(session):
    roby = getattr(setup_globals, "roby")

    plot.plotselect(roby)
    assert plot.get_plotted_counters() == ["axis:roby"]


def test_plotselect_alias(session):
    aliases = session.env_dict["ALIASES"]
    diode = getattr(setup_globals, "diode")
    foo = aliases.add("foo", diode.fullname)
    plotselect("foo")
    assert plot.get_plotted_counters() == [foo.fullname]

    plotselect("not_exists")
    assert plot.get_plotted_counters() == ["not_exists"]


def test_plotinit(session):
    diode = getattr(setup_globals, "diode")
    roby = getattr(setup_globals, "roby")
    sd = ScanDisplay()

    plotinit("foo")
    assert sd.get_next_scan_channels() == ["foo"]
    plotinit(roby)
    assert sd.get_next_scan_channels() == ["axis:roby"]
    plotinit(diode)
    assert sd.get_next_scan_channels() == [diode.fullname]
    plotinit(diode.fullname)
    assert sd.get_next_scan_channels() == [diode.fullname]

    plotinit(diode, roby)
    assert sd.get_next_scan_channels() == [diode.fullname, "axis:roby"]


def test_counter_argument_on_cen_com_peak(session):
    roby = getattr(setup_globals, "roby")
    diode = getattr(setup_globals, "diode")
    diode2 = getattr(setup_globals, "diode2")
    scans.ascan(roby, 0, .1, 5, 0, diode, diode2, save=False)
    cen(diode)
    cen(diode2)
    com(diode)
    com(diode2)
    peak(diode)
    peak(diode2)


def test_plotselect_and_global_cen(session):
    roby = getattr(setup_globals, "roby")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    plot.plotselect(simul_counter)
    scans.ascan(roby, 0, .1, 5, 0, simul_counter, save=False)
    assert simul_counter.fullname == scan_tools.get_selected_counter_name()
    cen_pos = scan_tools.cen()
    assert pytest.approx(0.05, abs=1e-3) == cen_pos

    # just call goto_X to go through the code
    scan_tools.goto_cen()
    scan_tools.goto_com()
    scan_tools.goto_peak()


def test_goto(session):
    from bliss.scanning.scan_tools import goto_cen, goto_com, goto_peak

    roby = session.config.get("roby")
    m0 = session.config.get("m0")
    simul_counter = session.config.get("sim_ct_gauss")
    diode = session.config.get("diode")

    s = scans.a2scan(roby, 0, 5, m0, -100, -50, 5, 0, simul_counter, diode, save=False)

    goto_cen(simul_counter)  # center of simul_counter
    assert pytest.approx(2.5, abs=1e-3) == roby.position
    assert pytest.approx(-75, abs=1) == m0.position

    goto_com(simul_counter)  # center of simul_counter
    assert pytest.approx(2.5, abs=1e-3) == roby.position
    assert pytest.approx(-75, abs=1) == m0.position

    goto_peak(simul_counter)  # center of simul_counter
    assert pytest.approx(2, abs=1e-3) == roby.position
    assert pytest.approx(-80, abs=1) == m0.position

    goto_cen(diode)
    roby_center = s.cen(diode, roby)
    m0_center = s.cen(diode, m0)
    assert pytest.approx(roby_center, abs=1e-3) == roby.position
    assert pytest.approx(m0_center, abs=1) == m0.position

    goto_com(diode)
    roby_centerofmass = s.com(diode, roby)
    m0_centerofmass = s.com(diode, m0)
    assert pytest.approx(roby_centerofmass, abs=1e-3) == roby.position
    assert pytest.approx(m0_centerofmass, abs=1) == m0.position

    goto_peak(diode)
    roby_peak = s.peak(diode, roby)
    m0_peak = s.peak(diode, m0)
    assert pytest.approx(roby_peak, abs=1e-3) == roby.position
    assert pytest.approx(m0_peak, abs=1) == m0.position

    # wrong arguments check
    with pytest.raises(TypeError):
        goto_cen(roby)  # first arg should be a counter
    with pytest.raises(TypeError):
        goto_cen("countername")
