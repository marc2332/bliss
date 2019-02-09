# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent

"""
Pytest list of tests
"""


def test_output_ramp(temp_tout):
    SP = 2
    val = temp_tout.read()
    print("Ramping from %s to %s" % (val, SP))
    temp_tout.ramp(SP)
    print("Wait for end of setpoint (around %s seconds)" % (int(abs(SP - val)) * 2))
    temp_tout.wait()
    myval = temp_tout.read()
    assert SP == pytest.approx(myval, temp_tout.deadband)


def test_output_ramp_with_kwarg(temp_tout):
    SP = 2
    KWRAMP = 20
    KWSTEP = 3
    KWDWELL = 5
    val = temp_tout.read()
    print("Ramping from %s to %s" % (val, SP))
    temp_tout.ramp(SP, ramp=KWRAMP, step=KWSTEP, dwell=KWDWELL)
    print("Wait for end of setpoint (around %s seconds)" % (int(abs(SP - val)) * 2))
    temp_tout.wait()
    myval = temp_tout.read()
    assert SP == pytest.approx(myval, temp_tout.deadband)
    print("check ramp value by kwargs")
    myramp = temp_tout.ramprate()
    assert myramp == KWRAMP
    mystep = temp_tout.step()
    assert mystep == KWSTEP
    mydwell = temp_tout.dwell()
    assert mydwell == KWDWELL


def test_output_ramp_stop(temp_tout):
    SP = 3
    val = temp_tout.read()
    print("Ramping (then stopping) from %s to %s" % (val, SP))
    temp_tout.ramp(SP)
    print("Stopping")
    temp_tout.stop()
    myval = temp_tout.read()
    print("Now at: %s" % myval)
    assert myval < SP
    assert temp_tout.state() == "READY"


def test_output_ramp_abort(temp_tout):
    SP = 4
    val = temp_tout.read()
    print("Ramping (then aborting) from %s to %s" % (val, SP))
    temp_tout.ramp(SP)
    print("Aborting")
    temp_tout.abort()
    myval = temp_tout.read()
    print("Now at: %s" % myval)
    assert myval < SP
    assert temp_tout.rampstate() == "READY"


def test_loop_output_ramp(temp_tloop):
    SP = 5
    val = temp_tloop.output.read()
    print("Ramping from %s to %s" % (val, SP))
    temp_tloop.output.ramp(SP)
    print("Wait for end of setpoint (around %s seconds)" % (int(abs(SP - val)) * 2))
    temp_tloop.output.wait()
    myval = temp_tloop.output.read()
    assert SP == pytest.approx(myval, temp_tloop.output.deadband)


def test_loop_output_ramp_stop(temp_tloop):
    SP = 6
    val = temp_tloop.output.read()
    print("Ramping (then stopping) from %s to %s" % (val, SP))
    temp_tloop.output.ramp(SP)
    assert temp_tloop.output.rampstate() == "RUNNING"
    gevent.sleep(0.1)
    print("Stopping")
    temp_tloop.output.stop()
    myval = temp_tloop.output.read()
    print("Now at: %s" % myval)
    assert myval < 6
    assert temp_tloop.output.rampstate() == "READY"


def test_loop_ramp(temp_tloop):
    SP = 3
    val = temp_tloop.output.read()
    print("Ramping from %s to %s" % (val, SP))
    temp_tloop.ramp(SP)
    print("Wait for end of setpoint (around %s seconds)" % (int(abs(SP - val)) * 2))
    temp_tloop.output.wait()
    myval = temp_tloop.output.read()
    assert SP == pytest.approx(myval, temp_tloop.output.deadband)
