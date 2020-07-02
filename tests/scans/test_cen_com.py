# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
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
import numpy
from collections import namedtuple
from scipy import signal


def test_pkcom_ascan_gauss(session):

    roby = getattr(setup_globals, "roby")
    m1 = getattr(setup_globals, "m1")
    diode = getattr(setup_globals, "diode")
    simul_counter = getattr(setup_globals, "sim_ct_gauss")

    s = scans.ascan(roby, 0, 10, 10, 0, simul_counter, save=False, return_scan=True)

    p = s.peak(simul_counter)
    fwhm = s.fwhm(simul_counter)
    c = s.com(simul_counter)

    assert pytest.approx(p) == 5
    assert pytest.approx(fwhm, abs=.01) == 4.57
    assert pytest.approx(c) == 5
    with pytest.raises(AssertionError):
        s.peak(simul_counter, m1)
    with pytest.raises(KeyError):
        s.peak(diode)

    s.goto_peak(simul_counter)
    assert pytest.approx(roby.position) == p
    s.goto_com(simul_counter)
    assert pytest.approx(roby.position) == c


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
    assert pytest.approx(p, abs=.01) == 4.57

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
    assert pytest.approx(p[robz], abs=.01) == 2.28
    assert pytest.approx(p[roby], abs=.01) == 4.57


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
    s = scans.ascan(ob.axis, 0, 1, ob.npoints, .01, ob.counter)
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
TestDataset = namedtuple("TestDataset", ["x", "y", "com", "cen", "fwhm"])
# if cen or com are None there will be no test for the concerned parameter

TestData = [
    TestDataset(
        numpy.arange(100),
        signal.gaussian(100, 10),
        pytest.approx(50, abs=1),
        pytest.approx(50, abs=1),
        pytest.approx(23.55, abs=.1),
    ),  # to test the test...
    TestDataset(
        numpy.array(
            [
                6.2483,
                6.2508,
                6.2583,
                6.2608,
                6.2733,
                6.2708,
                6.2733,
                6.2758,
                6.2783,
                6.2833,
                6.2908,
                6.2933,
                6.2983,
                6.3008,
                6.3083,
                6.3083,
                6.3133,
                6.3108,
                6.3208,
                6.3258,
                6.3283,
                6.3333,
                6.3383,
                6.3408,
                6.3458,
                6.3508,
                6.3558,
                6.3583,
                6.3633,
                6.3633,
                6.3708,
                6.3733,
                6.3733,
                6.3808,
                6.3858,
                6.3883,
                6.3958,
                6.3983,
                6.4008,
                6.4058,
                6.4108,
                6.4158,
                6.4183,
                6.4208,
                6.4258,
                6.4283,
                6.4308,
                6.4358,
                6.4433,
                6.4458,
                6.4483,
            ]
        ),
        numpy.array(
            [
                97509.2,
                97080.6,
                95261.3,
                95141.4,
                93604.9,
                93774.6,
                94248,
                94140.9,
                94378.8,
                96796.6,
                104079,
                110674,
                122297,
                134952,
                156822,
                164838,
                190479,
                170147,
                207026,
                224835,
                238949,
                260079,
                295097,
                339408,
                469760,
                635630,
                1.22468e+06,
                1.4857e+06,
                1.99651e+06,
                2.37889e+06,
                3.5033e+06,
                3.9517e+06,
                4.10261e+06,
                4.56964e+06,
                4.40632e+06,
                4.12317e+06,
                3.51486e+06,
                3.26117e+06,
                2.87866e+06,
                2.35846e+06,
                2.00371e+06,
                1.57291e+06,
                1.36902e+06,
                1.16209e+06,
                951301,
                845309,
                737104,
                629688,
                478522,
                417137,
                342809,
            ]
        ),
        pytest.approx(6.38, abs=.01),
        pytest.approx(6.38, abs=.1),
        pytest.approx(0.041, abs=.005),
    ),
    TestDataset(
        numpy.array(
            [
                0.0238095,
                0.0238095,
                0.0285714,
                0.0285714,
                0.0666667,
                0.0619048,
                0.0666667,
                0.0761905,
                0.0857143,
                0.0904762,
                0.0952381,
                0.0904762,
                0.0904762,
                0.0904762,
                0.0952381,
                0.0952381,
                0.0952381,
                0.0714286,
                0.0666667,
                0.0666667,
                0.0619048,
                0.0619048,
                0.0619048,
                0.0619048,
                0.0619048,
                0.0666667,
                0.0809524,
                0.0809524,
                0.0761905,
                0.0809524,
                0.0857143,
                0.0857143,
                0.0714286,
                0.0619048,
                0.0619048,
                0.0619048,
                0.0571429,
                0.0571429,
                0.0619048,
                0.0619048,
                0.0571429,
                0.0666667,
                0.0714286,
                0.0714286,
                0.0666667,
                0.0619048,
                0.052381,
                0.0380952,
                0.0380952,
                0.0380952,
                0.0380952,
            ]
        ),
        numpy.array(
            [
                97509.2,
                97080.6,
                95261.3,
                95141.4,
                93604.9,
                93774.6,
                94248,
                94140.9,
                94378.8,
                96796.6,
                104079,
                110674,
                122297,
                134952,
                156822,
                164838,
                190479,
                170147,
                207026,
                224835,
                238949,
                260079,
                295097,
                339408,
                469760,
                635630,
                1.22468e+06,
                1.4857e+06,
                1.99651e+06,
                2.37889e+06,
                3.5033e+06,
                3.9517e+06,
                4.10261e+06,
                4.56964e+06,
                4.40632e+06,
                4.12317e+06,
                3.51486e+06,
                3.26117e+06,
                2.87866e+06,
                2.35846e+06,
                2.00371e+06,
                1.57291e+06,
                1.36902e+06,
                1.16209e+06,
                951301,
                845309,
                737104,
                629688,
                478522,
                417137,
                342809,
            ]
        ),
        pytest.approx(0.06, abs=.01),
        None,
        None,
    ),
]


@pytest.mark.parametrize("real_test_data", TestData)
def test_cen_com_with_data(real_test_data):
    if real_test_data.com is not None:
        assert real_test_data.com == scan_math.com(real_test_data.x, real_test_data.y)
    if real_test_data.cen is not None:
        assert (
            real_test_data.cen
            == scan_math.cen(real_test_data.x, real_test_data.y).position
        )
    if real_test_data.fwhm is not None:
        assert (
            real_test_data.fwhm
            == scan_math.cen(real_test_data.x, real_test_data.y).fwhm
        )
