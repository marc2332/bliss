# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy


def test_autofilter_ascan(default_session):
    energy = default_session.config.get("energy")
    energy.move(16)

    autof = default_session.config.get("autof")
    filterw = default_session.config.get("filtW0")
    filterw.filter = 0
    sim = default_session.config.get("sim_diffraction_peak")

    s = autof.ascan(sim.axis, 0, 1, sim.npoints, .1, sim.counter, autof, save=False)

    scan_data = s.get_data()

    # test that all nessesary counters are published
    assert "TestFilterCounterAxis:value" in scan_data
    assert "TestFilterCounterAxis:value_corr" in scan_data
    assert "autof:curratt" in scan_data
    assert "autof:transm" in scan_data

    # test that the corrected values are the expected ones
    assert numpy.allclose(scan_data["TestFilterCounterAxis:value_corr"], sim._data)

    # test that transm fits to measured value
    assert numpy.allclose(
        scan_data["TestFilterCounterAxis:value"] / scan_data["autof:transm"],
        scan_data["TestFilterCounterAxis:value_corr"],
    )

    # test that all filters are out at beginning and end of scan
    assert scan_data["autof:transm"][0] == 1.0
    # assert scan_data["autof:transm"][-1] == 1.0
    # to be checked why this is not the case!


def test_autofilter_api(default_session):
    # just call once all functions that are relevant to the user in autof
    # and filtW0 that are not related to a scan

    # get ready
    energy = default_session.config.get("energy")
    energy.move(16)

    autof = default_session.config.get("autof")
    filterw = default_session.config.get("filtW0")

    # change filter
    filterw.filter = 0
    assert autof.transmission == 1
    filterw.filter = 2
    # Transmission of 20um Cu at 16keV roughly 0.327 according to
    # http://henke.lbl.gov/optical_constants/filter2.html
    assert autof.transmission == pytest.approx(0.327, abs=.005)

    # change energy and see if transmission is updated
    filterw.filter = 2
    trans_16keV = autof.transmission
    energy.move(12)
    trans_12keV = autof.transmission
    assert trans_16keV != trans_12keV

    # Todos:
    # - autof.check_filter (what is the expected behaviour of this)
    # - autof.energy_axis  (in case it should be exchangable on runtime)
    # - autof.??
    # - filterw.??
