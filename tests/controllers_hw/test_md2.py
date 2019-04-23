# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
from tests.controllers_hw.conftest import beacon_beamline


#  MD2 Micro Difractometer hardware test

#  Axes in this device have always the same name
test_axes = ["phix", "phiy", "phiz", "sampx", "sampy"]


@pytest.fixture
def axis(axis_name, beacon_beamline):
    """Getting axis object from the configured beamline and properly close it"""
    axis = beacon_beamline.get(axis_name)
    try:
        yield axis
    finally:
        axis.close()


@pytest.mark.parametrize("axis_name", test_axes)
def test_md2_axis_non_invasive(axis, axis_name):
    """Non invasive checking of MD2 axis"""

    #  Check hardware state
    assert axis.controller._get_hwstate() == "Ready"
    #  Check software state
    assert axis.controller._get_swstate() == "Ready"


@pytest.mark.parametrize("axis_name", test_axes)
def test_md2_axis_invasive(axis, axis_name):
    """Invasive checking of MD2 axis"""

    #  Initialize axis
    axis.controller._initialize_axis(axis)
    #  Check position
    assert isinstance(axis.controller.read_position(axis), float)
