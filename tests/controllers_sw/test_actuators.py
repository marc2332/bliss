# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.common.actuator import AbstractActuator, ActuatorState


@pytest.fixture
def simulation_actuator():
    simulation_actuator_state = {"in": False}

    def set_in(state=simulation_actuator_state):
        state["in"] = True

    def set_out(state=simulation_actuator_state):
        state["in"] = False

    return AbstractActuator(set_in, set_out)


@pytest.fixture
def simulation_actuator_with_timeout():
    simulation_actuator_state = {"in": False}

    def set_in(state=simulation_actuator_state):
        gevent.sleep(0.5)

    return AbstractActuator(set_in)


def test_simulation_actuator(simulation_actuator):
    assert simulation_actuator.state == "UNKNOWN"
    simulation_actuator.set_in()
    assert simulation_actuator.is_in()
    assert simulation_actuator.state == "IN"
    simulation_actuator.set_out()
    assert simulation_actuator.is_out()
    assert simulation_actuator.state == "OUT"
    with simulation_actuator:
        assert simulation_actuator.is_in()
    assert simulation_actuator.is_out()
    simulation_actuator.open()
    assert simulation_actuator.is_in()
    simulation_actuator.close()
    assert simulation_actuator.is_out()
    simulation_actuator.toggle()
    assert simulation_actuator.is_in()
    simulation_actuator.toggle()
    assert simulation_actuator.is_out()


def test_actuator_timeout(simulation_actuator_with_timeout):
    simulation_actuator = simulation_actuator_with_timeout
    with pytest.raises(gevent.Timeout):
        simulation_actuator.set_in(timeout=0.2)
    simulation_actuator._check = False
    simulation_actuator.set_in()
    assert simulation_actuator.is_in()


def test_actuator(beacon):
    simulation_actuator = beacon.get("actuator")

    assert simulation_actuator.state == "UNKNOWN"
    simulation_actuator.set_in()
    assert simulation_actuator.is_in()
    assert simulation_actuator.state == "IN"
    simulation_actuator.set_out()
    assert simulation_actuator.is_out()
    assert simulation_actuator.state == "OUT"
    with simulation_actuator:
        assert simulation_actuator.is_in()
    assert simulation_actuator.is_out()
    simulation_actuator.open()
    assert simulation_actuator.is_in()
    simulation_actuator.close()
    assert simulation_actuator.is_out()
    simulation_actuator.toggle()
    assert simulation_actuator.is_in()
    simulation_actuator.toggle()
    assert simulation_actuator.is_out()
