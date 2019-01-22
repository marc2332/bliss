# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
VSCANNER controller hardware test.

Run with:
    $ pytest --axis-name <axis-name> ..../test_VSCANNER.py

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


def test_hw_vscan_axis_init(axis):
    axis.controller._initialize_axis(axis)


def test_hw_vscan_read_position(axis):
    pos = axis.position


def test_hw_vscan_get_identifier(axis):
    vscan_id = axis.controller.get_id(axis)
    print(f"Vscanner ID={vscan_id}")


def test_hw_vscan_axis_move(axis):
    axis.sync_hard()
    start_position = axis.position
    axis.move(start_position + 1.0)
    end_position = axis.position
    try:
        assert start_position + 1.0 == pytest.approx(end_position, 0.01)
    finally:
        axis.move(start_position)
