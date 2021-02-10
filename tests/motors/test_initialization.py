# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import sys
import os
import pytest
from unittest import mock

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


def test_axis_disable_broken_init(default_session):
    def faulty_initialize(*args, **kwargs):
        raise RuntimeError("FAILED TO INITIALIZE")

    with mock.patch(
        "bliss.controllers.motors.mockup.Mockup.initialize_axis",
        wraps=faulty_initialize,
    ):
        roby = default_session.config.get("roby")
        with pytest.raises(RuntimeError):
            roby.state
        assert roby.disabled

        # try to enable while motor cannot be initialized still
        with pytest.raises(RuntimeError):
            roby.enable()
        assert roby.disabled

    assert roby.disabled
    # motor stays disabled until .enable() is called
    # all calls doing a lazy init will fail immediately
    # without accessing hw
    roby.enable()
    assert "READY" in roby.state
    assert not roby.disabled


def test_broken_controller_init(default_session):
    def faulty_initialize(*args, **kwargs):
        raise RuntimeError("FAILED TO INITIALIZE")

    with mock.patch(
        "bliss.controllers.motors.mockup.Mockup.initialize", wraps=faulty_initialize
    ):
        with pytest.raises(RuntimeError):
            default_session.config.get("roby")

        with pytest.raises(RuntimeError, match="Controller is disabled"):
            default_session.config.get("roby")

    with mock.patch(
        "bliss.controllers.motors.mockup.Mockup.initialize_hardware",
        wraps=faulty_initialize,
    ):
        roby = default_session.config.get("roby")
        assert roby

        with pytest.raises(RuntimeError):
            roby.position  # will call initialize_hardware => will fail
        # axis roby stays disabled
        # controller stays disabled

    # roby and robu are on the same controller ;
    # controller is disabled because hardware init failed
    with pytest.raises(RuntimeError, match="Controller is disabled"):
        default_session.config.get("robu")

    with pytest.raises(RuntimeError, match="Axis roby is disabled"):
        # axis is already disabled
        roby.position

    with pytest.raises(RuntimeError, match="Controller is disabled"):
        roby.enable()


def test_encoder_disable_broken_init(default_session):
    def faulty_initialize(*args, **kwargs):
        raise RuntimeError("FAILED TO INITIALIZE")

    with mock.patch(
        "bliss.controllers.motors.mockup.Mockup.initialize_encoder",
        wraps=faulty_initialize,
    ):
        m1 = default_session.config.get(
            "m1"
        )  # have to get axis first, because mockup does not know how to retrieve axis from encoder, if there is no axis there is no encoder pos. unless explicitely set
        enc = default_session.config.get("m1enc")
        with pytest.raises(RuntimeError):
            enc.raw_read
        assert enc.disabled

        # try to enable while motor cannot be initialized still
        with pytest.raises(RuntimeError):
            enc.enable()
        assert enc.disabled

    assert enc.disabled
    # encoder stays disabled until .enable() is called
    # all calls doing a lazy init will fail immediately
    # without accessing hw
    enc.enable()
    assert enc.raw_read == 0.0
    assert not enc.disabled


def test_initialized_cache(beacon):
    roby = beacon.get("roby")
    llbend1 = beacon.get("llbend1")

    # /!\ check roby and llbend1 are on 2 different mockup controller instances
    assert type(roby.controller) == type(llbend1.controller)
    assert roby.controller != llbend1.controller

    roby_controller_init_cache = channels.Cache(roby.controller, "initialized")
    llbend1_controller_init_cache = channels.Cache(llbend1.controller, "initialized")
    assert roby_controller_init_cache != llbend1_controller_init_cache
    assert roby_controller_init_cache.name != llbend1_controller_init_cache.name

    # check that another motor on the same controller has the same 'initialized' cache
    m1 = beacon.get("m1")
    assert roby.controller == m1.controller
    m1_controller_init_cache = channels.Cache(m1.controller, "initialized")
    assert m1_controller_init_cache == roby_controller_init_cache
