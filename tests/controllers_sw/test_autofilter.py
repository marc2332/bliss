# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy


def test_autofilter_ascan_basics(default_session):
    energy = default_session.config.get("energy")
    energy.move(16)

    autof = default_session.config.get("autof")
    sim = default_session.config.get("sim_diffraction_peak")

    s = autof.ascan(sim.axis, 0, 1, sim.npoints, .1, sim.counter, save=False)


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
    assert scan_data["autof:transm"][-1] == 1.0
