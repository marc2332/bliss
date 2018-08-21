# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

SP = 10
KW = 1

"""
Pytest list of tests
"""


def test_read_input(temp_tin):
    print "%s" % (temp_tin.read())


def test_input_state(temp_tin):
    temp_tin.state()


def test_output_state(temp_tout):
    temp_tout.state()


def test_output_limits(temp_tout):
    assert -1 == temp_tout.limits[0]


def test_output_deadband(temp_tout):
    assert 0.1 == temp_tout.deadband


def test_read_output(temp_tout):
    print "%s" % (temp_tout.read())


def test_read_input_from_loop(temp_tloop):
    print "%s" % (temp_tloop.input.read())


def test_read_output_from_loop(temp_tloop):
    print "%s" % (temp_tloop.output.read())


def test_set_ramprate(temp_tout):
    SP = 10
    temp_tout.ramprate(SP)
    val = temp_tout.ramprate()
    assert SP == val


def test_set_stepval(temp_tout):
    SP = 5
    temp_tout.step(SP)
    val = temp_tout.step()
    assert SP == val


def test_set_dwell(temp_tout):
    SP = 2
    temp_tout.dwell(SP)
    val = temp_tout.dwell()
    assert SP == val


def test_output_set(temp_tout):
    SP = 1
    val = temp_tout.read()
    print "Direct setpoint from %s to %s" % (val, SP)
    temp_tout.set(SP)
    temp_tout.wait()
    myval = temp_tout.read()
    assert SP == pytest.approx(myval, 1e-02)


def test_output_set_with_kwarg(temp_tout):
    SP = 0
    KW = 23
    val = temp_tout.read()
    print "Direct setpoint from %s to %s" % (val, SP)
    temp_tout.set(SP, step=KW)
    temp_tout.wait()
    myval = temp_tout.read()
    assert SP == pytest.approx(myval, 1e-02)
    myset = temp_tout.set()
    assert SP == pytest.approx(myset, 1e-02)
    myval = temp_tout.step()
    assert myval == KW


def test_loop_set(temp_tloop):
    SP = 3
    val = temp_tloop.output.read()
    print "Direct setpoint from %s to %s" % (val, SP)
    temp_tloop.set(SP)
    temp_tloop.output.wait()
    myval = temp_tloop.output.read()
    assert SP == pytest.approx(myval, 1e-02)


def test_loop_regulation(temp_tloop):
    print "starting regulation"
    temp_tloop.on()
    print "Stopping regulation"
    temp_tloop.off()


def test_kp(temp_tloop):
    KW = 13
    print "Setting P to %f" % KW
    temp_tloop.kp(KW)
    myval = temp_tloop.kp()
    assert KW == myval


def test_ki(temp_tloop):
    KW = 50
    print "Setting I to %f" % KW
    temp_tloop.ki(KW)
    myval = temp_tloop.ki()
    assert KW == myval


def test_kd(temp_tloop):
    KW = 1
    print "Setting D to %f" % KW
    temp_tloop.kd(KW)
    myval = temp_tloop.kd()
    assert KW == myval


def test_read_input_counter(temp_tin):
    myval = temp_tin.read()
    print "%s" % (myval)
    myvalcount = temp_tin.counter.read()
    assert myval == pytest.approx(myvalcount, 1e-02)


def test_read_output_counter(temp_tout):
    myval = temp_tout.read()
    print "%s" % (myval)
    myvalcount = temp_tout.counter.read()
    assert myval == pytest.approx(myvalcount, 1e-02)
