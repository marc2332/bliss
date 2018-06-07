# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common.measurement import BaseCounter

def test_lima_simulator(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert simulator.camera
    assert simulator.acquisition
    assert simulator.image

    trigger_mode = simulator.acquisition.trigger_mode
    try:
        simulator.acquisition.trigger_mode = 'INTERNAL_TRIGGER_MULTI'
        assert simulator.acquisition.trigger_mode == 'INTERNAL_TRIGGER_MULTI'
        assert simulator.acquisition.trigger_mode == \
        simulator.acquisition.trigger_mode_enum.INTERNAL_TRIGGER_MULTI
    finally:
        simulator.acquisition.trigger_mode = trigger_mode

    assert isinstance(simulator.image, BaseCounter)

    assert simulator.camera.test == 'test'

def test_lima_sim_bpm(beacon, lima_simulator):
    simulator = beacon.get("lima_simulator")

    assert pytest.raises(RuntimeError, "simulator.bpm")

    assert 'bpm' not in simulator.counters._fields
    assert 'bpm' not in simulator.counter_groups._fields

    
