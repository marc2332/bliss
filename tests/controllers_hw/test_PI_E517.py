# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PI E-51x: E-517 E-518 piezo controllers hardware test.

Run with:
    $ pytest --axis-name <axis-name> ..../test_PI_E517.py

"""
import time
import pytest


@pytest.fixture
def axis(request, beacon_beamline):
    """
    Function to access axis given as parameter in test command line.
    """
    axis_name = request.config.getoption("--axis-name")
    test_axis = beacon_beamline.get(axis_name)
    try:
        yield test_axis
    finally:
        test_axis.close()


def test_hw_axis_init(axis):
    """
    Hardware initialization
    Device must be present.
    Use axis fixture.
    """
    axis.sync_hard()
    axis.controller._initialize_axis(axis)


def test_hw_read_position(axis):
    """
    Read position (cache ?)
    """
    pos = axis.position
    assert pos


# called at end of each test
def tearDown(self):
    # Little wait time to let time to PI controller to
    # close peacefully its sockets ???
    time.sleep(0.1)
