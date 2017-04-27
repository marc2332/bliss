# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

@pytest.fixture
def robz(beacon):
  m = beacon.get("robz")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def roby(beacon):
  m = beacon.get("roby")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def robz2(beacon):
  m = beacon.get("robz2")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def m0(beacon):
  m = beacon.get("m0")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def jogger(beacon):
  m = beacon.get("jogger")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

