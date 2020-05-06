# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import sys
import os
import pytest

from bliss.config import channels
from bliss.config.static import get_config
from bliss.controllers.motor import Controller as MotController


class DummyCtrl(MotController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.init_order = list()
        self.init_axis_order = list()

    def initialize(self):
        self.init_order.append("S")

    def initialize_hardware(self):
        self.init_order.append("H")

    def initialize_axis(self, axis):
        self.init_axis_order.append("S")

    def initialize_hardware_axis(self, axis):
        self.init_axis_order.append("H")

    def set_velocity(self, *args):
        pass

    def read_velocity(self, *args):
        return 0.0

    def set_acceleration(self, *args):
        pass

    def read_acceleration(self, *args):
        return 0.0


@pytest.fixture
def dummy_axis_1(beacon):
    sys.path.append(os.path.dirname(__file__))
    yield beacon.get("dummy_axis_1")
    sys.path.pop()


def test_initialization_controller_order(dummy_axis_1):
    dummy_axis_1.position  # init everything
    assert dummy_axis_1.controller.init_order == ["S", "H"]


def test_initialization_axis_order(dummy_axis_1):
    dummy_axis_1.position  # init everything
    assert dummy_axis_1.controller.init_axis_order == ["S", "H"]


def test_motor_shared(beacon):
    """
    Simulating motor shared between two sessions
    The second instance should be able to get the configuration
    while the first session is moving the motor
    """
    config = get_config()
    roby1 = config.get("roby")
    config._clear_instances()
    roby1.move(0, wait=False)
    channels.clear_cache(roby1, roby1.controller)
    roby1.controller._Controller__initialized_axis[roby1] = False
    roby2 = config.get("roby")
    roby2.__info__()
    roby1.stop()
