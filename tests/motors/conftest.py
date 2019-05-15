# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def motor_fixture(name):
    def get_motor(beacon):
        m = beacon.get(name)
        yield m
        m.__close__()

    get_motor.__name__ = name
    return pytest.fixture(get_motor)


def calc_motor_fixture(name):
    def get_motor(beacon):
        m = beacon.get(name)
        yield m
        m.__close__()

    get_motor.__name__ = name
    return pytest.fixture(get_motor)


robz = motor_fixture("robz")
roby = motor_fixture("roby")
robz2 = motor_fixture("robz2")
m0 = motor_fixture("m0")
m1 = motor_fixture("m1")
jogger = motor_fixture("jogger")
omega = motor_fixture("omega")
hooked_m0 = motor_fixture("hooked_m0")
hooked_m1 = motor_fixture("hooked_m1")
hooked_error_m0 = motor_fixture("hooked_error_m0")
s1ho = calc_motor_fixture("s1ho")
s1hg = calc_motor_fixture("s1hg")
s1vo = calc_motor_fixture("s1vo")
s1vg = calc_motor_fixture("s1vg")
s1f = motor_fixture("s1f")
s1b = motor_fixture("s1b")
s1u = motor_fixture("s1u")
s1d = motor_fixture("s1d")
calc_mot1 = calc_motor_fixture("calc_mot1")
_calc_mot2 = calc_motor_fixture("calc_mot2")
custom_axis = motor_fixture("custom_axis")

# this ensures .__close__() is called
# for calc_mot1 when calc_mot2 is used
@pytest.fixture
def calc_mot2(calc_mot1, _calc_mot2):
    yield _calc_mot2


@pytest.fixture
def m1enc(beacon):
    m = beacon.get("m1enc")
    yield m
