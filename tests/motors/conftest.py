# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from contextlib import contextmanager


@contextmanager
def motor_context(beacon, name):
    m = beacon.get(name)
    yield m
    m.stop()
    m.wait_move()
    m.apply_config()
    m.controller.set_hw_limits(m, None, None)
    m.dial(0)
    m.position(0)
    beacon.reload()

@contextmanager
def calc_motor_context(beacon, name):
    m = beacon.get(name)
    m.no_offset = False
    yield m
    m.stop()
    m.wait_move()
    # m.apply_config()


@pytest.fixture
def robz(beacon):
    with motor_context(beacon, 'robz') as m:
        yield m


@pytest.fixture
def roby(beacon):
    with motor_context(beacon, 'roby') as m:
        yield m


@pytest.fixture
def robz2(beacon):
    with motor_context(beacon, 'robz2') as m:
        yield m


@pytest.fixture
def m0(beacon):
    with motor_context(beacon, 'm0') as m:
        yield m


@pytest.fixture
def jogger(beacon):
    with motor_context(beacon, 'jogger') as m:
        yield m


@pytest.fixture
def m1(beacon):
    with motor_context(beacon, 'm1') as m:
        yield m


@pytest.fixture
def s1ho(beacon):
    with calc_motor_context(beacon, "s1ho") as m:
        yield m


@pytest.fixture
def s1hg(beacon):
    with calc_motor_context(beacon, "s1hg") as m:
        yield m


@pytest.fixture
def s1vo(beacon):
    with calc_motor_context(beacon, "s1vo") as m:
        yield m


@pytest.fixture
def s1vg(beacon):
    with calc_motor_context(beacon, "s1vg") as m:
        yield m


@pytest.fixture
def s1f(beacon):
    with motor_context(beacon, "s1f") as m:
        yield m


@pytest.fixture
def s1b(beacon):
    with motor_context(beacon, "s1b") as m:
        yield m


@pytest.fixture
def s1u(beacon):
    with motor_context(beacon, "s1u") as m:
        yield m


@pytest.fixture
def s1d(beacon):
    with motor_context(beacon, "s1d") as m:
        yield m


@pytest.fixture
def m1enc(beacon):
    m = beacon.get("m1enc")
    yield m
