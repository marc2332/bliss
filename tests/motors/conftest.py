# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent


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
m2 = motor_fixture("m2")
jogger = motor_fixture("jogger")
omega = motor_fixture("omega")
hooked_m0 = motor_fixture("hooked_m0")
hooked_m1 = motor_fixture("hooked_m1")
hooked_error_m0 = motor_fixture("hooked_error_m0")
hooked_error_m1 = motor_fixture("hooked_error_m1")
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
calc_mot3 = calc_motor_fixture("calc_mot3")
custom_axis = motor_fixture("custom_axis")
mono = motor_fixture("mono")
energy = calc_motor_fixture("energy")
wavelength = calc_motor_fixture("wavelength")
mot_maxee = motor_fixture("mot_maxee")
nsa = motor_fixture("nsa")

# this ensures .__close__() is called
# for calc_mot1 when calc_mot2 is used
@pytest.fixture
def calc_mot2(calc_mot1, _calc_mot2):
    yield _calc_mot2


@pytest.fixture
def m1enc(beacon):
    m = beacon.get("m1enc")
    yield m


@pytest.fixture
def m2enc(beacon):
    m = beacon.get("m2enc")
    yield m


@pytest.fixture
def bad_motor(beacon):
    bad = beacon.get("bad")
    bad.controller.bad_start = False
    bad.controller.bad_state = False
    bad.controller.bad_state_after_start = False
    bad.controller.bad_stop = False
    bad.controller.bad_position = False
    bad.dial = 0
    bad.position = 0
    bad.sync_hard()
    yield bad


def wait_state(mot, state, timeout=1, stop_exception=None):
    """
    :param mot Axis, Group, ...:
    :param str state: "MOVING", "READY", ...
    """
    try:
        with gevent.Timeout(timeout, TimeoutError):
            if state == "READY":
                if stop_exception:
                    with pytest.raises(stop_exception):
                        mot.wait_move()
                else:
                    mot.wait_move()
            else:
                while state not in mot.state:
                    gevent.sleep(0.010)
    except TimeoutError:
        AssertionError(
            f"state {repr(state)} not reached within {timeout} second (current state: {repr(mot.state)})"
        )

    # Check Axis state API consistency:
    mot_state = mot.state
    is_moving = mot.is_moving
    if state == "MOVING":
        assert is_moving
    else:
        assert not is_moving
    assert state in mot_state
    assert getattr(mot_state, state)
