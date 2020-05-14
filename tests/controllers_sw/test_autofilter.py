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
    sim = default_session.config.get("sim_diffraction_peak")

    s = autof.ascan(sim.axis, 0, 1, sim.npoints, .1, sim.counter, save=False)

    assert "TestFilterCounterAxis:value" in s.get_data()
    assert "TestFilterCounterAxis:value_corr" in s.get_data()

    assert numpy.allclose(s.get_data()["TestFilterCounterAxis:value_corr"], sim._data)
