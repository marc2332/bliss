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
from bliss.shell.standard import (
    plotselect,
    plotinit,
    cen,
    com,
    peak,
    fwhm,
    find_position,
    goto_custom,
)
from bliss.scanning.scan_display import ScanDisplay
from bliss.scanning import scan_tools, scan_math
from bliss.common import plot
from bliss.controllers.simulation_counter import FixedShapeCounter
from tests.test_profiles import test_profiles


def test_pkcom_ascan_gauss(session):

    roby = getattr(setup_globals, "roby")
    m1 = getattr(setup_globals, "m1")
    diode = getattr(setup_globals, "diode")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.ascan(roby, 0, 10, 10, 0, simul_counter, save=False, return_scan=True)

    peak = s.peak(simul_counter)
    cen = s.cen(simul_counter)
    fwhm = s.fwhm(simul_counter)
    com = s.com(simul_counter)

    if False:
        # For debugging
        x, y = s._get_x_y_data(simul_counter, roby)
        _plot_cen_com(x, y, cen=cen, com=com, fwhm=fwhm, title="sim_ct_gauss")

    assert pytest.approx(peak) == 5
    assert pytest.approx(com) == 5
    assert pytest.approx(cen) == 5
    assert pytest.approx(fwhm, abs=.01) == 4.07
    with pytest.raises(AssertionError):
        s.peak(simul_counter, m1)
    with pytest.raises(KeyError):
        s.peak(diode)

    s.goto_peak(simul_counter)
    assert pytest.approx(roby.position) == peak
    s.goto_com(simul_counter)
    assert pytest.approx(roby.position) == com


def test_pkcom_a2scan_gauss(session):

    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.a2scan(
        roby, 0, 10, robz, 0, 5, 10, 0, simul_counter, save=False, return_scan=True
    )

    p = s.peak(simul_counter, roby)
    assert pytest.approx(p) == 5

    p = s.cen(simul_counter, roby)
    assert pytest.approx(p) == 5

    p = s.com(simul_counter, roby)
    assert pytest.approx(p) == 5

    p = s.fwhm(simul_counter, roby)
    assert pytest.approx(p, abs=.01) == 4.07

    p = s.peak(simul_counter)
    assert p[robz] == 2.5
    assert p[roby] == 5
    assert (
        p.__info__() == "{roby: 5.0, robz: 2.5}"
        or p.__info__() == "{robz: 2.5, roby: 5.0}"
    )

    p = s.cen(simul_counter)
    assert p[robz] == 2.5
    assert p[roby] == 5
    assert (
        p.__info__() == "{roby: 5.0, robz: 2.5}"
        or p.__info__() == "{robz: 2.5, roby: 5.0}"
    )

    p = s.com(simul_counter)
    assert p[robz] == pytest.approx(2.5, abs=.01)
    assert p[roby] == pytest.approx(5, abs=.01)
    assert (
        p.__info__() == "{roby: 5.0, robz: 2.5}"
        or p.__info__() == "{robz: 2.5, roby: 5.0}"
    )

    p = s.fwhm(simul_counter)
    assert pytest.approx(p[robz], abs=.01) == 2.03
    assert pytest.approx(p[roby], abs=.01) == 4.07


def test_pkcom_timescan_gauss(session):

    center = 0.1 * 10 / 2
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.timescan(0.1, simul_counter, npoints=10, save=False, return_scan=True)

    p = s.peak(simul_counter)
    assert pytest.approx(p, abs=.1) == center


def test_plotselect1(session):
    mg = session.env_dict["ACTIVE_MG"]  # counts diode2 and diode3
    roby = getattr(setup_globals, "roby")

    simul_counter1 = getattr(setup_globals, "diode2")
    simul_counter2 = getattr(setup_globals, "diode3")
    simul_counter4 = getattr(setup_globals, "diode4")

    # Select counter via library function
    plot.plotselect(simul_counter1)
    scans.ascan(roby, 0, .1, 5, 0, mg, simul_counter4, save=False)

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


def test_plotselect_template_axis(session):
    plot.plotselect("*:roby")
    assert plot.get_plotted_counters() == ["axis:roby"]


def test_plotselect_template_diode(session):
    diode = getattr(setup_globals, "diode")
    diode2 = getattr(setup_globals, "diode2")
    plot.plotselect("*diode*")
    assert diode.fullname in plot.get_plotted_counters()
    assert diode2.fullname in plot.get_plotted_counters()


def test_plotselect_template_not_twice(session):
    roby = getattr(setup_globals, "roby")
    plot.plotselect("*:roby", roby)
    assert plot.get_plotted_counters().count("axis:roby") == 1


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
    assert sd.next_scan_displayed_channels == ["foo"]
    plotinit(roby)
    assert sd.next_scan_displayed_channels == ["axis:roby"]
    plotinit(diode)
    assert sd.next_scan_displayed_channels == [diode.fullname]
    plotinit(diode.fullname)
    assert sd.next_scan_displayed_channels == [diode.fullname]

    plotinit(diode, roby)
    assert sd.next_scan_displayed_channels == [diode.fullname, "axis:roby"]


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
    fwhm(diode)

    with pytest.raises(RuntimeError):
        cen()

    scans.ascan(roby, 0, .1, 5, 0, diode, save=False)
    cen()
    com()
    peak()
    fwhm()


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

    roby.move(3)
    m0.move(-78)

    goto_com(simul_counter)  # center of simul_counter
    assert pytest.approx(2.5, abs=1e-3) == roby.position
    assert pytest.approx(-75, abs=1) == m0.position

    roby.move(3)
    m0.move(-78)

    goto_peak(simul_counter)  # center of simul_counter
    assert pytest.approx(2, abs=1e-3) == roby.position
    assert pytest.approx(-80, abs=1) == m0.position

    ## use scan attached functions as well
    s.goto_cen(simul_counter)  # center of simul_counter
    assert pytest.approx(2.5, abs=1e-3) == roby.position
    assert pytest.approx(-75, abs=1) == m0.position

    roby.move(3)
    m0.move(-78)

    s.goto_com(simul_counter)  # center of simul_counter
    assert pytest.approx(2.5, abs=1e-3) == roby.position
    assert pytest.approx(-75, abs=1) == m0.position

    roby.move(3)
    m0.move(-78)

    s.goto_peak(simul_counter)  # center of simul_counter
    assert pytest.approx(2, abs=1e-3) == roby.position
    assert pytest.approx(-80, abs=1) == m0.position

    goto_cen(diode)
    roby_center = s.cen(diode, roby)
    m0_center = s.cen(diode, m0)
    assert pytest.approx(roby_center, abs=1e-3) == roby.position
    assert pytest.approx(m0_center, abs=1) == m0.position

    roby.move(3)
    m0.move(-78)

    goto_com(diode)
    roby_centerofmass = s.com(diode, roby)
    m0_centerofmass = s.com(diode, m0)
    assert pytest.approx(roby_centerofmass, abs=1e-3) == roby.position
    assert pytest.approx(m0_centerofmass, abs=1) == m0.position

    roby.move(3)
    m0.move(-78)

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


def test_com_with_neg_y(default_session):
    ob = FixedShapeCounter()
    ob.signal = "sawtooth"
    s = scans.ascan(ob.axis, 0, 1, ob.nsteps, .01, ob.counter)
    com = s.com(ob.counter, axis=ob.axis)
    assert pytest.approx(com, abs=.0001) == 0.5987


def test_find_position_goto_custom(session):
    counter = session.config.get("sim_ct_gauss")
    roby = session.config.get("roby")

    def special_com(x, y):
        return numpy.average(x, weights=y)

    # test on scan object
    s = scans.ascan(roby, 0, 1, 15, .01, counter, save=False)
    assert s.find_position(special_com, counter) == pytest.approx(.5, abs=.01)
    s.goto_custom(special_com, counter)
    assert roby.position == pytest.approx(.5, abs=.01)

    roby.move(.7)

    # test in bliss.shell.standard
    assert find_position(special_com) == pytest.approx(.5, abs=.01)
    goto_custom(special_com)
    assert roby.position == pytest.approx(.5, abs=.01)

    roby.move(.7)

    # test custom stuff from setup file
    assert session.env_dict["find_special"]() == pytest.approx(.5, abs=.01)
    session.env_dict["goto_special"]()
    assert roby.position == pytest.approx(.5, abs=.01)


@pytest.mark.parametrize("data", test_profiles.experimental_data())
def test_cen_com_with_data(data):
    if data.com is None:
        com = None
    else:
        com = scan_math.com(data.x, data.y)

    if data.cen is None:
        cen = None
    else:
        cen = scan_math.cen(data.x, data.y).position

    if data.fwhm is None:
        fwhm = None
    else:
        fwhm = scan_math.cen(data.x, data.y).fwhm

    title = data.name

    if False:
        # For debugging
        x, y = data.x, data.y
        _plot_cen_com(x, y, cen=cen, com=com, fwhm=fwhm, title=title)

    assert com == data.com, title
    assert cen == data.cen, title
    assert fwhm == data.fwhm, title


@pytest.mark.parametrize(
    "counter_signal", test_profiles.theoretical_profile_parameters()
)
def test_cen_com_with_signals(default_session, counter_signal):
    tca = FixedShapeCounter()
    tca.signal = title = counter_signal.name
    s = scans.ascan(tca.axis, 0, 1, tca.nsteps, .01, tca.counter, save=False)

    com = s.com(tca.counter, axis=tca.axis)
    cen = s.cen(tca.counter, axis=tca.axis)
    fwhm = s.fwhm(tca.counter, axis=tca.axis)

    if False:
        # For debugging
        x, y = s._get_x_y_data(tca.counter, tca.axis)
        _plot_cen_com(x, y, cen=cen, com=com, fwhm=fwhm, title=title)

    assert com == counter_signal.com, title
    assert cen == counter_signal.cen, title
    assert fwhm == counter_signal.fwhm, title


def _plot_cen_com(x, y, com=None, cen=None, fwhm=None, title="", savedir=False):
    """For debugging the tests
    """
    import matplotlib.pyplot as plt
    from scipy.interpolate import interp1d

    if savedir:
        plt.figure(figsize=(4, 3))
    else:
        plt.figure()

    ymin = numpy.nanmin(y)
    ymax = numpy.nanmax(y)

    if cen is not None and fwhm is not None:
        xa, xb = cen - fwhm / 2, cen + fwhm / 2
        mask = (x >= xa) & (x <= xb)
        f = interp1d(x, y, bounds_error=False, assume_sorted=False)
        x1 = numpy.concatenate([[xa], x[mask], [xb]])
        y1 = f(x1)
        y2 = numpy.full_like(y1, ymin)
        plt.fill_between(x1, y1, y2, alpha=0.3)

    plt.plot(x, y, "-o")
    if com is not None:
        plt.axvline(com, label="com", color="r")
    if cen is not None:
        plt.axvline(cen, label="cen", color="g")
    if cen is not None and fwhm is not None:
        plt.axvline(xa, label="fwhm", color="b")
        plt.axvline(xb, color="b")

    for f in [0.12, 0.5, 0.88]:
        plt.axhline(ymin + (ymax - ymin) * f)

    if title:
        plt.title(title)
    plt.legend()
    if savedir:
        plt.savefig(f"{savedir}/{title.replace(' ', '_')}.png")
    else:
        plt.show()
