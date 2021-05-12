# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy

from bliss.controllers.simulation_counter import (
    OneDimSimulationCounter,
    OneDimSimulationController,
)
from bliss.common.counter import SamplingMode
from bliss.common.scans import loopscan


def test_onedim_simulation_counter__linear_up():
    controller = OneDimSimulationController(name="onedim")
    c1 = OneDimSimulationCounter(
        "c1", controller=controller, signal="linear_up", coef=10, size=5
    )
    data = controller.read(c1)
    expected = numpy.array([0, 2.5, 5, 7.5, 10])
    numpy.testing.assert_array_equal(data, expected)


def test_onedim_simulation_counter__gaussian():
    controller = OneDimSimulationController(name="onedim")
    c1 = OneDimSimulationCounter(
        "c1", controller=controller, signal="gaussian", coef=10, size=5
    )
    data = controller.read(c1)
    expected = numpy.array([1.35, 6.07, 10., 6.07, 1.35])
    numpy.testing.assert_array_almost_equal(data, expected, decimal=2)


def test_onedim_simulation_counter__acquisition(session):
    """Check acaquisition from a OneDimSimulationCounter"""
    controller = OneDimSimulationController(name="onedim")
    counter = OneDimSimulationCounter(
        "onedim", controller, signal="linear_up", coef=10, size=5
    )

    assert counter.mode == SamplingMode.SINGLE

    loops = loopscan(5, .1, counter, save=False)
    data = loops.get_data()["onedim"]

    expected = numpy.array([0., 2.5, 5., 7.5, 10.])
    assert len(data) == 5
    numpy.testing.assert_array_equal(data[0], expected)
    numpy.testing.assert_array_equal(data[-1], expected)
