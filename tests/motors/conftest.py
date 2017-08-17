# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from contextlib import contextmanager

def motor_fixture(name):
    def get_motor(beacon):
        m = beacon.get(name)
        yield m
        m.stop()
        m.wait_move()
        m.apply_config()
        m.controller.set_hw_limits(m, None, None)
        m.dial(0)
        m.position(0)
        for hook in m.motion_hooks:
            hook.nb_pre_move = 0
            hook.nb_post_move = 0
    get_motor.__name__ = name
    return pytest.fixture(get_motor)


def calc_motor_fixture(name):
    def get_motor(beacon):
        m = beacon.get(name)
        m.no_offset = False
        yield m
        m.stop()
        m.wait_move()
    get_motor.__name__ = name
    return pytest.fixture(get_motor)


robz = motor_fixture('robz')
roby = motor_fixture('roby')
robz2 = motor_fixture('robz2')
m0 = motor_fixture('m0')
m1 = motor_fixture('m1')
jogger = motor_fixture('jogger')
hooked_m0 = motor_fixture('hooked_m0')
hooked_m1 = motor_fixture('hooked_m1')
hooked_error_m0 = motor_fixture('hooked_error_m0')
s1ho = calc_motor_fixture('s1ho')
s1hg = calc_motor_fixture('s1hg')
s1vo = calc_motor_fixture('s1vo')
s1vg = calc_motor_fixture('s1vg')
s1f = motor_fixture('s1f')
s1b = motor_fixture('s1b')
s1u = motor_fixture('s1u')
s1d = motor_fixture('s1d')


@pytest.fixture
def m1enc(beacon):
    m = beacon.get("m1enc")
    yield m
