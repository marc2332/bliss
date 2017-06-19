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

@pytest.fixture
def m1(beacon):
  m = beacon.get("m1")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def m1enc(beacon):
  m = beacon.get("m1enc")
  yield m

@pytest.fixture
def s1ho(beacon):
  m = beacon.get("s1ho")
  m.no_offset = False
  yield m
  m.stop()
  m.wait_move()
  #m.apply_config()

@pytest.fixture
def s1hg(beacon):
  m = beacon.get("s1hg")
  m.no_offset = False
  yield m
  m.stop()
  m.wait_move()
  #m.apply_config()

@pytest.fixture
def s1vo(beacon):
  m = beacon.get("s1vo")
  m.no_offset = False
  yield m
  m.stop()
  m.wait_move()
  #m.apply_config()

@pytest.fixture
def s1vg(beacon):
  m = beacon.get("s1vg")
  m.no_offset = False
  yield m
  m.stop()
  m.wait_move()
  #m.apply_config()

@pytest.fixture
def s1f(beacon):
  m = beacon.get("s1f")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def s1b(beacon):
  m = beacon.get("s1b")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def s1u(beacon):
  m = beacon.get("s1u")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

@pytest.fixture
def s1d(beacon):
  m = beacon.get("s1d")
  yield m
  m.stop()
  m.wait_move()
  m.apply_config()
  m.controller.set_hw_limits(m, None, None)
  m.dial(0); m.position(0)

