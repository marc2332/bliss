# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
PI E-753 piezo controller hardware test.

Run with:
    $ pytest --axis-name <axis-name> ..../test_PI_E753.py

"""
import pytest
import time
import gevent
import os


@pytest.fixture
def axis(request, beacon_beamline):
    axis_name = request.config.getoption("--axis-name")
    axis = beacon_beamline.get(axis_name)
    try:
        yield axis
    finally:
        axis.close()


def test_hw_axis_init(axis):
    axis.controller._initialize_axis(axis)


def test_hw_read_position(axis):
    pos = axis.position


# called at end of each test
def tearDown(self):
    # Little wait time to let time to PI controller to
    # close peacefully its sockets ???
    time.sleep(0.1)
