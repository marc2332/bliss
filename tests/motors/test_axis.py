# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import re
import time
import math
import numpy
import gevent
import gevent.event
from bliss.common import event
from bliss.common.standard import mv
from bliss.common.hook import MotionHook
from bliss.common.axis import Modulo, AxisState
from unittest import mock
import random
import inspect


def test_property_setting(robz):
    assert robz.velocity == 100


def test_controller_from_axis(robz):
    assert robz.controller.name == "test"


def test_state_callback(robz):
    ready_event = gevent.event.AsyncResult()

    def callback(state):
        ready_event.set(state.READY)

    event.connect(robz, "state", callback)

    robz.rmove(1)

    assert ready_event.get(timeout=0.1)
    assert robz.state.READY


def test_info(robz, capsys):
    assert robz.controller.name == "test"
    captured = robz.__info__()

    output = "AXIS:\n"
    output += "     name (R): robz\n"
    output += "     unit (R): mm\n"
    output += "     offset (R): 0.00000\n"
    output += "     backlash (R): 0.00000\n"
    output += "     sign (R): 1\n"
    output += "     steps_per_unit (R): 10000.00\n"
    output += "     tolerance (R) (to check pos. before a move): 0.0001\n"
    # output += "     motion_hooks (R): []\n"
    output += "     limits (RW):    Low: -1000.00000 High: 1000000000.00000    (config Low: -1000.00000 High: 1000000000.00000)\n"
    output += "     dial (RW): 0.00000\n"
    output += "     position (RW): 0.00000\n"
    output += "     state (R): READY (Axis is READY)\n"
    # output += "     _hw_position (R): 0.00000\n"
    # output += "     hw_state (R): READY (Axis is READY)\n"
    output += "     acceleration (RW):  300.00000  (config:  300.00000)\n"
    output += "     acctime (RW):         0.33333  (config:    0.33333)\n"
    output += "     velocity (RW):      100.00000  (config:  100.00000)\n"
    output += "Controller name: test\n"
    output += "MOCKUP AXIS:\n"
    output += "    this axis (robz) is a simulation axis\n"
    output += "ENCODER:\n     None\n"

    # # output += "controller: <bliss.controllers.motors.mockup.Mockup object at 0x7f78ac843d30>\n"
    # output += "Axis: robz\n"
    # output += "Controller:\n"
    # output += "  class: <class 'bliss.controllers.motors.mockup.Mockup'>\n"
    # output += "  name: test\n"

    # remove "controller" line because 0x7f78ac843d30 ref is not deterministic...
    captured = re.sub(
        "<bliss.controllers.motors.mockup.Mockup object at.*\n", "", captured
    )

    assert captured == output


def test_move_done_callback(robz):
    ready_event = gevent.event.AsyncResult()
    dial_event = gevent.event.AsyncResult()

    def callback(move_done):
        if move_done:
            ready_event.set(robz.is_moving is False)
            dial_event.set(robz.dial)

    event.connect(robz, "move_done", callback)

    robz.rmove(1)

    assert ready_event.get(timeout=0.1)
    assert dial_event.get() == 1

    event.disconnect(robz, "move_done", callback)


def test_position_callback(robz):
    storage = {"last_pos": None, "last_dial_pos": None}

    def callback(pos, old=storage):
        old["last_pos"] = pos

    def dial_callback(pos, old=storage):
        old["last_dial_pos"] = pos

    event.connect(robz, "position", callback)
    event.connect(robz, "dial_position", dial_callback)

    robz.position = 1
    pos = robz.position
    robz.rmove(1)
    assert storage["last_pos"] == pytest.approx(pos + 1)
    assert storage["last_dial_pos"] == pytest.approx(robz.user2dial(pos + 1))


def test_position_callback2(default_session):
    nsa = default_session.config.get("nsa")

    class Callback:
        def __init__(self, motor):
            self._motor = motor

        def __call__(self, position, signal=None, sender=None):
            print(self._motor.position)

    cbk = Callback(nsa)

    event.connect(nsa, "position", cbk)

    with gevent.Timeout(1):
        nsa.move(2)


def test_position_callback_with_exception(roby, calc_mot1):
    # Init
    roby.position
    calc_mot1.position
    # issue 719
    def callback(pos):
        raise RuntimeError("Nasty exception")

    event.connect(roby, "position", callback)

    try:
        roby.move(.1)
    except RuntimeError:
        pytest.fail("Unwanted exception")

    assert "READY" in roby.state

    event.disconnect(roby, "position", callback)
    event.connect(calc_mot1, "position", callback)

    # check calc_mot1 is at 2.0 since it depends on roby
    # (an exception in callback should not affect the calc mot)
    assert calc_mot1.position == pytest.approx(.2)

    # now do the opposite: move calc and see how it behaves with
    # exception raised in callback
    event.connect(calc_mot1, "position", callback)

    try:
        calc_mot1.move(.1)
    except RuntimeError:
        pytest.fail("Unwanted exception")

    assert "READY" in calc_mot1.state
    assert roby.position == pytest.approx(0.05)


def test_invalid_move(robz):

    # test axis move
    with pytest.raises(RuntimeError):
        robz.move(math.nan)

    # test group move
    with pytest.raises(RuntimeError):
        mv(robz, math.nan)

    with pytest.raises(RuntimeError):
        robz.move(numpy.array([math.nan]))

    target_pos = numpy.array([3.0])
    robz.move(target_pos)
    assert robz.position == target_pos


def test_rmove(robz):
    robz.move(0)
    assert robz.position == pytest.approx(0)
    robz.rmove(0.1)
    robz.rmove(0.1)
    assert robz.position == pytest.approx(0.2)


def test_acceleration(robz):
    robz.acceleration = 1
    assert robz.acceleration == 1
    robz.acceleration = numpy.array([2])
    assert robz.acceleration == 2

    acc = robz.acceleration
    assert robz.acctime == pytest.approx(robz.velocity / robz.acceleration)

    v = robz.velocity / 2.0
    robz.velocity = v

    assert robz.acceleration == pytest.approx(acc)
    assert robz.acctime == pytest.approx(v / acc)

    robz.acctime = 0.03
    assert robz.acceleration == pytest.approx(v / 0.03)

    assert robz.config_acceleration == pytest.approx(300)


def test_axis_set_acctime(roby):
    roby.acctime = 0.250
    assert roby.acctime == 0.25
    roby.acctime = numpy.array([0.3])
    assert roby.acctime == 0.3


def test_axis_move(robz):
    assert robz.state.READY

    robz.move(180, wait=False)

    assert robz.state.MOVING

    robz.wait_move()

    assert robz.state.READY

    assert robz.position == 180
    assert robz._set_position == 180

    robz.move(numpy.array([181]))
    assert robz.position == 181


def test_axis_multiple_move(robz):
    robz.velocity = 1000
    robz.acceleration = 10000
    for i in range(10):
        assert robz.state.READY
        robz.move((i + 1) * 2, wait=False)
        assert robz.state.MOVING
        robz.wait_move()
        assert robz.state.READY


def test_axis_init(robz):
    assert robz.state.READY
    assert robz.controller._axes_data[robz]["init_count"] == 1


def test_stop(robz):
    assert robz.state.READY

    robz.move(180, wait=False)

    assert robz._set_position == 180

    assert robz.state.MOVING

    robz.stop()

    assert robz.state.READY


@pytest.mark.flaky(reruns=3, reason="issue2353")
def test_asynchronous_stop(robz):
    robz.velocity = 1

    robz.move(180, wait=False)

    assert robz.state.MOVING

    started_time = time.time()
    time.sleep(1 + robz.acctime)

    robz.stop(wait=False)

    elapsed_time = time.time() - started_time
    assert robz.state.MOVING

    robz.wait_move()

    assert robz.state.READY

    assert robz.position == pytest.approx(
        elapsed_time + robz.acceleration * robz.acctime ** 2, 1e-2
    )


def test_home_stop(robz):
    robz.home(wait=False)

    time.sleep(0.1)

    assert robz.state.MOVING

    robz.stop()

    robz.wait_move()

    assert robz.state.READY


"""
HARDWARE LIMITS
"""


def test_hardware_limits(roby):
    try:
        roby.controller.set_hw_limits(roby, -2, 2)
        with pytest.raises(RuntimeError):
            roby.move(3)

        assert pytest.approx(roby.position) == 2

        # move hit limit because of backlash
        with pytest.raises(RuntimeError):
            roby.move(0)

        assert pytest.approx(roby.position) == 0

        roby.move(1)

        assert roby.position == 1
    finally:
        roby.controller.set_hw_limits(roby, None, None)


def test_limit_search(robz):
    robz.controller.set_hw_limits(robz, -11.5, 12.4)
    robz.hw_limit(1)
    assert robz.dial == 12.4
    robz.hw_limit(-1)
    assert robz.dial == -11.5


def test_limit_search_stop(robz):
    robz.controller.set_hw_limits(robz, -5, 5)
    robz.hw_limit(1, wait=False)

    time.sleep(0.1)

    assert robz.state.MOVING

    robz.stop()
    robz.wait_move()

    assert robz.state.READY


"""
SOFTWARE LIMITS
"""
"""
- name: robz
    steps_per_unit: 10000
    velocity: 100
    acceleration: 300
    low_limit: -1000
    high_limit: 1000000000.0
    unit: mm
- name: roby
    backlash: 2
    steps_per_unit: 10000
    velocity: 2500.0
    acceleration: 1000.0
    low_limit: -.inf
    high_limit: .inf
    default_cust_attr: 6.28
"""


def test_limits(robz):
    iset_pos = robz._set_position
    robz.limits = -1, 1
    assert robz.limits == (-1, 1)
    with pytest.raises(ValueError):
        robz.move(1.1)
    assert robz._set_position == iset_pos
    with pytest.raises(ValueError):
        robz.move(-1.1)
    assert robz._set_position == iset_pos
    robz.limits = -2.1, 1.1
    robz.rmove(1)
    robz.rmove(-2)
    assert robz.state.READY


def test_dial_limits(robz):
    robz.dial = 10
    robz.position = 0
    robz.dial_limits = None, None
    assert robz.limits == (-numpy.inf, numpy.inf)
    robz.dial_limits = 0, 20
    assert robz.limits == (-10, 10)


def test_limits_offset(robz):
    # check that user limits are the same than dial limits from config.
    assert robz.limits == (-1000, 1e9)

    # change limits (new limits given in user units)
    robz.limits = numpy.array([-90, 90])
    assert robz.limits == (-90, 90)
    robz.limits = (-100, 100)
    assert robz.limits == (-100, 100)
    assert robz.config_limits == (-1000, 1e9)

    # add an offset by 5 user units.
    _init_pos_robz = robz.position
    robz.position = _init_pos_robz + 5
    assert robz.offset == 5
    assert robz.limits == (-95, 105)
    assert robz.limits == (-95, 105)


def test_limits2(robz, roby):
    iset_pos = robz._set_position
    assert robz.limits == (-1000, 1e9)
    assert roby.limits == (float("-inf"), float("+inf"))
    with pytest.raises(ValueError):
        robz.move(-1001)
    assert robz._set_position == iset_pos


def test_limits3(robz):
    robz.limits = -10, 10
    robz.position = 10
    assert robz.limits == (0, 20)
    assert robz._set_position == 10


"""
BACKLASH
"""


def test_backlash(roby):
    roby.move(-10, wait=False)

    assert roby.backlash_move == -12

    roby.wait_move()

    assert roby.position == -10

    roby.move(-9)

    roby.limits = -11, 10

    with pytest.raises(ValueError):
        roby.move(-10)


def test_interrupted_backlash(roby):
    roby.move(-1, wait=False)

    roby._group_move._backlash_started_event.wait()

    # have to kill twice because backlash move is protected
    roby._group_move._move_task.kill(KeyboardInterrupt, block=False)
    roby._group_move._move_task.kill(KeyboardInterrupt, block=False)
    with pytest.raises(KeyboardInterrupt):
        roby.wait_move()

    # backlash move is interrupted before it finishes
    assert roby.position < -1
    assert "READY" in roby.state


def test_backlash2(roby):
    roby.move(1, wait=False)
    assert roby.backlash_move == 0
    roby.wait_move()
    assert roby.position == 1


def test_backlash3(roby):
    roby.position = 1
    assert roby.position == 1

    roby.move(1, wait=False)

    assert roby.backlash_move == 0

    roby.wait_move()
    assert roby.state.READY


def test_backlash4(roby):
    position_with_many_digits = -0.1515151515
    roby.move(position_with_many_digits)
    assert roby.backlash_move == -2 + position_with_many_digits
    p1 = roby.position
    # motor could not move to this exact position
    assert not math.isclose(p1, position_with_many_digits)
    # moving again should not trig a backlash move
    roby.move(position_with_many_digits)
    assert roby.backlash_move == 0
    # and finally, it should stay where it is
    p2 = roby.position
    assert p1 == p2


def test_backlash_stop(roby):
    t = time.time()
    roby.acctime = 0.1
    roby.move(-1000, wait=False)
    assert roby.backlash_move == -1002
    time.sleep(0.2)
    # calculate stop position
    roby.stop(wait=False)
    stop_pos = roby._hw_position - roby.acceleration * 0.5 * roby.acctime ** 2
    roby.wait_move()

    assert pytest.approx(roby.dial, 1e-1) == stop_pos + roby.backlash
    assert roby._set_position == roby.dial
    assert roby.state.READY


def test_backlash_prop(roby, robz):
    assert robz.backlash == 0
    assert roby.backlash

    robz.backlash = roby.backlash
    robz.position = -9
    robz.limits = -11, 0
    with pytest.raises(ValueError):
        robz.move(-10)
    robz.backlash = 0
    robz.move(-10)


def test_axis_steps_per_unit(roby):
    roby.move(180, wait=False)
    roby.wait_move()
    assert roby.target_pos == roby.steps_per_unit * 180


def test_axis_set_pos(roby):
    roby.position = 10
    assert roby.position == pytest.approx(10)
    ipos = roby.position
    fpos = 10
    ilow_lim, ihigh_lim = roby.limits = -100, 100
    roby.position = numpy.array([fpos * 2])
    assert roby.position == pytest.approx(2 * fpos)
    assert roby._set_position == pytest.approx(2 * fpos)
    roby.position = fpos
    assert roby.position == pytest.approx(fpos)
    assert roby._set_position == pytest.approx(fpos)
    dpos = fpos - ipos
    flow_lim, fhigh_lim = roby.limits
    dlow_lim, dhigh_lim = flow_lim - ilow_lim, fhigh_lim - ihigh_lim
    assert dlow_lim == pytest.approx(dpos)
    assert dhigh_lim == pytest.approx(dpos)


def test_axis_set_velocity(roby):
    # vel is in user-unit per seconds.
    roby.velocity = 5000
    assert roby.velocity == 5000
    roby.velocity = numpy.array([6000])
    assert roby.velocity == 6000
    assert roby.config_velocity == 2500


def test_custom_method(roby):
    roby.Set_Closed_Loop(True)
    roby.Set_Closed_Loop(False)
    roby.Set_Closed_Loop()


def test_home_search(roby):
    roby.home(wait=False)
    assert roby.state.MOVING
    roby.wait_move()
    assert roby.state.READY
    roby.dial = 38930
    roby.position = 38930
    assert roby.offset == 0
    assert roby.position == 38930


def test_ctrlc(robz, capsys, log_shell_mode):  # noqa: F811
    robz.move(100, wait=False)
    assert robz.state.MOVING
    assert robz.is_moving
    time.sleep(0.1)
    robz._group_move._move_task.kill(KeyboardInterrupt, block=False)

    with pytest.raises(KeyboardInterrupt):
        robz.wait_move()

    assert not robz.is_moving
    assert robz.state.READY
    assert robz.position < 100
    assert robz._set_position == robz.position


def test_simultaneous_move(robz):
    # this test, before the bug was found, was *sometimes*
    # giving discrepancy error instead of MOVING state error
    move_started = gevent.event.Event()

    def start_move(target):
        robz.move(target, wait=False)
        move_started.set()
        robz.wait_move()

    try:
        move_greenlet = gevent.spawn(start_move, 10)
        move_started.wait()
        assert robz.state.MOVING
        with pytest.raises(Exception) as exc:
            robz.move(-10)
        assert "MOVING" in str(exc.value)
    finally:
        move_greenlet.get()


def test_simultaneous_waitmove_exception(robz):
    robz.move(100, wait=False)
    w1 = gevent.spawn(robz.wait_move)
    w2 = gevent.spawn(robz.wait_move)
    time.sleep(0.2)
    robz._group_move._move_task.kill(RuntimeError, block=False)
    with pytest.raises(RuntimeError):
        w1.get()
    with pytest.raises(RuntimeError):
        w2.get()
    robz.off()
    assert "OFF" in robz.state
    robz.on()
    assert "READY" in robz.state


def test_on_off(robz):
    robz.off()
    assert robz.state.OFF
    with pytest.raises(RuntimeError):
        robz.move(1)
    robz.on()
    assert robz.state.READY
    robz.move(1)
    assert robz.position == pytest.approx(1)
    robz.move(2, wait=False)
    with pytest.raises(RuntimeError):
        robz.off()
    robz.wait_move()
    robz.off()
    assert robz.state.OFF


def test_dial(robz):
    robz.position = 1
    assert robz.dial == 0
    assert robz.position == 1
    robz.position = robz.dial
    assert robz.position == 0
    robz.dial = 1
    assert robz.dial == 1
    assert robz.position == 0
    robz.position = robz.dial = 2
    assert robz.dial == 2
    assert robz.position == 2
    robz.position = numpy.array([3])
    assert robz.position == 3
    robz.dial = numpy.array([3])
    assert robz.dial == 3


def test_set_position(m0):
    assert m0.steps_per_unit == 1
    assert m0.position == m0._set_position
    m0.rmove(0.1)
    assert m0._set_position == 0.1
    for i in range(9):
        m0.rmove(0.1)
    assert m0._set_position == pytest.approx(1.0)
    assert m0.position == pytest.approx(m0._set_position)
    m0.move(0.4)
    assert m0._set_position == 0.4
    assert m0.position == 0
    m0.rmove(0.6)
    assert m0._set_position == 1
    assert m0.position == m0._set_position
    m0.move(2, wait=False)
    time.sleep(0.01)
    m0._group_move._move_task.kill(KeyboardInterrupt, block=False)
    try:
        m0.wait_move()
    except KeyboardInterrupt:
        pass
    m0.move(1)
    assert m0._set_position == 1


def test_interrupted_waitmove(m0):
    m0.move(100, wait=False)
    waitmove = gevent.spawn(m0.wait_move)
    time.sleep(0.01)
    with pytest.raises(KeyboardInterrupt):
        kill_pos = m0.position
        waitmove.kill(KeyboardInterrupt)
    time.sleep(0.1)
    assert m0.position == pytest.approx(kill_pos)
    assert m0.state.READY


def test_no_offset(roby):
    try:
        roby.no_offset = True
        roby.move(0)
        roby.position = 1
        assert roby.dial == 1
        roby.dial = 0
        assert roby.position == 0
    finally:
        roby.no_offset = False


@pytest.mark.parametrize("motor_name", ["roby", "nsa"])
def test_offset_property(beacon, motor_name):
    mot = beacon.get(motor_name)

    mot.move(1)

    mot.offset = -1

    assert mot.position == 0
    assert mot.dial == 1
    dll, dhl = mot.dial_limits
    assert mot.limits == (dll - 1, dhl - 1)


@pytest.mark.parametrize("motor_name", ["roby", "nsa"])
def test_sign_property(beacon, motor_name):
    mot = beacon.get(motor_name)

    mot.move(1)

    mot.sign = -1

    assert mot.position == -1
    dll, dhl = mot.dial_limits
    assert mot.limits == (-dll, -dhl)


@pytest.mark.parametrize("motor_name", ["roby", "nsa"])
def test_settings_to_config(beacon, motor_name):
    mot = beacon.get(motor_name)
    cfg = beacon.get_config(motor_name)
    cfg_acc = cfg.get("acceleration")
    cfg_vel = cfg.get("velocity")
    cfg_ll = cfg.get("low_limit")
    cfg_hl = cfg.get("high_limit")

    mot.velocity = 3
    mot.acceleration = 10
    mot.limits = None, None
    assert mot.config_velocity == cfg_vel
    assert mot.config_acceleration == cfg_acc
    assert mot.config_limits == (cfg_ll, cfg_hl)
    mot.settings_to_config()
    try:
        assert mot.config_velocity == 3
        assert mot.config_acceleration == 10
        assert mot.config_limits == (float("-inf"), float("inf"))
    finally:
        # put back config files as they were,
        # since the fixture that starts
        # all servers (and that copy config. to a temp folder
        # for the test) has a session scope
        mot.velocity = cfg_vel
        mot.acceleration = cfg_acc
        mot.low_limit = cfg_ll
        mot.high_limit = cfg_hl
        mot.settings_to_config()


@pytest.mark.parametrize("motor_name", ["roby", "nsa"])
def test_apply_config(beacon, motor_name):
    mot = beacon.get(motor_name)
    cfg = beacon.get_config(motor_name)
    cfg_acc = cfg.get("acceleration")
    cfg_vel = cfg.get("velocity")
    cfg_limits = (
        cfg.get("low_limit", float("-inf")),
        cfg.get("high_limit", float("+inf")),
    )

    mot.velocity = 1
    mot.acceleration = 2
    mot.limits = 0, 10
    mot.apply_config()
    assert mot.velocity == cfg_vel
    assert mot.acceleration == cfg_acc
    assert mot.limits == cfg_limits


@pytest.mark.flaky(reruns=3, reason="issue2353")
def test_jog(robz):
    robz.velocity = 10
    robz.jog_velocity = 300
    assert robz.jog_velocity == 300
    robz.jog()
    t = 1 + robz.jog_acctime
    start_time = time.time()
    time.sleep(t)
    hw_position = robz._hw_position
    elapsed_time = (time.time() - start_time) - robz.jog_acctime
    assert hw_position == pytest.approx(
        300 * elapsed_time + robz.acceleration * 0.5 * robz.jog_acctime ** 2, 1e-2
    )
    assert robz.state.MOVING
    robz.stop()
    assert robz.stop_jog_called
    assert robz.state.READY
    assert robz._set_position == robz.position
    robz.dial = 0
    robz.position = 0
    assert robz.velocity == 10
    robz.jog(-300, reset_position=0)
    assert robz.jog_velocity == -300
    start_time = time.time()
    time.sleep(t)
    hw_position = robz._hw_position
    elapsed_time = (time.time() - start_time) - robz.jog_acctime
    assert hw_position == pytest.approx(
        -300 * elapsed_time - robz.acceleration * 0.5 * robz.jog_acctime ** 2, 1e-2
    )
    robz.stop()
    assert robz.dial == 0
    assert robz.velocity == 10
    robz.jog_velocity = 300
    robz.jog(reset_position=Modulo())
    time.sleep(t)
    robz.stop()
    hw_position = (0.6666 * robz.jog_velocity * (1 + 2 * robz.jog_acctime)) % 360
    assert robz.dial == pytest.approx(hw_position, 0.1)


def test_jog2(jogger):
    jogger.jog(
        300
    )  # this should go in the opposite direction because steps_per_unit < 0
    t = 1 + jogger.jog_acctime
    start_time = time.time()
    time.sleep(t)
    hw_position = jogger._hw_position
    elapsed_time = (time.time() - start_time) - jogger.jog_acctime
    assert hw_position == pytest.approx(
        300 * elapsed_time + jogger.acceleration * 0.5 * jogger.jog_acctime ** 2, 1e-2
    )
    jogger.stop()


def test_jog3(robz):
    robz.jog_velocity = 100
    robz.velocity = 1
    saved_velocity = robz.velocity
    assert robz.acctime / robz.jog_acctime == pytest.approx(1 / robz.jog_velocity)
    robz.jog()
    time.sleep(0.2 + robz.jog_acctime)
    robz.jog_velocity = 300
    assert robz.is_moving
    # ensure controller has really changed speed
    assert robz.controller.read_velocity(robz) / abs(
        robz.steps_per_unit
    ) == pytest.approx(300)
    robz.stop()
    assert robz.velocity == saved_velocity


def test_jog_method_change_velocity_and_stop(robz):
    robz.jog_velocity = 300
    robz.jog()
    time.sleep(0.2 + robz.jog_acctime)
    assert robz.is_moving
    robz.jog_velocity = 0
    assert not robz.is_moving
    robz.jog(300)
    assert robz.jog_velocity == 300
    assert robz.is_moving
    robz.jog(0)
    assert not robz.is_moving


def test_measured_position(m1, roby):
    assert m1.measured_position == m1.position
    with pytest.raises(RuntimeError):
        roby.measured_position


def test_axis_no_state_setting(m1):
    m1.move(1, relative=True)  # store settings
    state = m1.state  # cache

    with mock.patch.object(m1.controller, "state") as new_state:
        new_state.return_value = AxisState("FAULT")
        assert m1.state == state
        assert m1.hw_state == AxisState("FAULT")
        m1.settings.disable_cache("state")
        assert m1.state == AxisState("FAULT")
        # re-enable cache
        new_state.return_value = AxisState("READY")
        m1.settings.disable_cache("state", False)
        assert m1.hw_state == AxisState("READY")
        # the beacon channel has been removed, there is no source of data
        # so this will read the hw_state
        assert m1.state == m1.hw_state
        new_state.return_value = AxisState("FAULT")
        assert m1.state == AxisState("READY")


def test_axis_disable_cache_settings_from_config(beacon):
    m1 = beacon.get("mot_1_disable_cache")
    m2 = beacon.get("mot_2_disable_cache")

    mot1_state = m1.state  # init
    mot1_position = m1.position
    mot2_state = m2.state  # init
    # initialize position
    m2.position

    # test no cache on both motors
    with mock.patch.object(m1.controller, "state") as new_state:
        new_state.return_value = AxisState("FAULT")
        assert m1.state == AxisState("FAULT")
        assert m2.state == AxisState("FAULT")

    # test no cache on position for mot2 and cache for mot1
    with mock.patch.object(m1.controller, "read_position") as new_position:
        position = random.random()
        new_position.return_value = position
        assert m1.position == mot1_position
        assert m2.position == pytest.approx(position / m2.steps_per_unit)


def test_object_methode_signatures_and_docstr(m0):
    assert inspect.getdoc(m0.get_voltage) == "doc-str of get_voltage"
    assert str(inspect.signature(m0.set_voltage)) == "(voltage)"
    assert inspect.getdoc(m0.set_voltage) == "doc-str of set_voltage"
    assert str(inspect.signature(m0.get_voltage)) == "()"
    assert inspect.getdoc(m0.custom_get_chapi) == "doc-str of custom_get_chapi"
    assert str(inspect.signature(m0.custom_get_chapi)) == "(value)"
    assert inspect.getdoc(m0.custom_park) == "doc-str of custom_park"
    assert str(inspect.signature(m0.custom_park)) == "()"


def test_user_msg(roby):
    motion_obj = roby.get_motion(1)
    assert motion_obj.user_msg == "Moving roby from 0 to 1"

    class CancelMove(Exception):
        pass

    # install a motion hook to receive motion objects
    class UserMsgCheckHook(MotionHook):
        def pre_move(self, motion_list):
            raise CancelMove(motion_list[0].user_msg)

    user_msg_hook = UserMsgCheckHook()
    user_msg_hook._add_axis(roby)
    roby.motion_hooks.append(user_msg_hook)

    with pytest.raises(CancelMove) as user_msg:
        roby.hw_limit(1)
    assert str(user_msg.value) == "Moving roby from 0 to lim+"
    with pytest.raises(CancelMove) as user_msg:
        roby.hw_limit(-1)
    assert str(user_msg.value) == "Moving roby from 0 to lim-"
    with pytest.raises(CancelMove) as user_msg:
        roby.home(1)
    assert str(user_msg.value) == "Moving roby from 0 to home"
    with pytest.raises(CancelMove) as user_msg:
        roby.home(-1)
    assert str(user_msg.value) == "Moving roby from 0 to home"
    with pytest.raises(CancelMove) as user_msg:
        roby.jog(10)
    assert (
        str(user_msg.value)
        == "Moving roby from 0 until it is stopped, at constant velocity in positive direction: 10.0\n"
        "To stop it: roby.stop()"
    )


def test_no_hardware_access_if_at_pos(robz):
    robz.move(1)

    with mock.patch.object(
        robz.controller, "read_position", return_value=1. * robz.steps_per_unit
    ) as read_position:
        robz.move(1)
        read_position.assert_not_called()

    with mock.patch.object(
        robz.controller, "state", return_value=AxisState("READY")
    ) as read_state:
        robz.move(1)
        read_state.assert_not_called()


def test_issue_1494(beacon):
    nsa = beacon.get("nsa")

    assert nsa.low_limit == -5.0
    assert nsa.high_limit == 5.0

    nsa.limits = (-1, 1)

    assert nsa.low_limit == -1.0
    assert nsa.high_limit == 1.0


def test_no_settings_offset(beacon):
    nsa = beacon.get("nsa")

    assert nsa.position == 0
    nsa.offset = 1
    assert nsa.position == pytest.approx(1)
    assert nsa.dial == pytest.approx(0)


def test_invalid_config(beacon):
    invalid_cfg = beacon.get_config("invalid_cfg_axis")

    invalid_mot = beacon.get("invalid_cfg_axis")
    with pytest.raises(RuntimeError) as exc:
        invalid_mot.position  # lazy init
    assert "velocity" in str(exc.value)

    invalid_cfg["velocity"] = 1
    with pytest.raises(RuntimeError) as exc:
        invalid_mot.position  # lazy init
    assert "acceleration" in str(exc.value)

    invalid_cfg["acceleration"] = 1
    with pytest.raises(RuntimeError) as exc:
        invalid_mot.position  # lazy init
    assert "steps_per_unit" in str(exc.value)

    invalid_cfg["steps_per_unit"] = 1
    assert invalid_mot.position == 0


def test_no_settings_hw_read_acc_vel_pos_state(nsa):
    cfg_vel = nsa.config_velocity
    cfg_acc = nsa.config_acceleration

    assert nsa.state == AxisState("READY")

    with mock.patch.object(nsa.controller, "state", return_value=AxisState("OFF")):
        assert nsa.state == AxisState("OFF")

    assert nsa.velocity == cfg_vel

    with mock.patch.object(nsa.controller, "read_velocity", return_value=888):
        assert nsa.velocity == pytest.approx(888 / nsa.steps_per_unit)
        nsa.velocity = 0
        assert nsa.config.config_dict["velocity"] == cfg_vel
        assert nsa.settings.get("velocity") is None
        assert nsa.velocity == pytest.approx(888 / nsa.steps_per_unit)

    assert nsa.acceleration == cfg_acc

    with mock.patch.object(nsa.controller, "read_acceleration", return_value=888):
        assert nsa.acceleration == pytest.approx(888 / nsa.steps_per_unit)
        nsa.acceleration = 0
        assert nsa.config.config_dict["acceleration"] == cfg_acc
        assert nsa.settings.get("acceleration") is None
        assert nsa.acceleration == pytest.approx(888 / nsa.steps_per_unit)

    assert nsa.position == 0

    with mock.patch.object(nsa.controller, "read_position", return_value=888):
        assert nsa.settings.get("position") is None
        assert nsa.settings.get("dial_position") is None
        assert nsa.position == pytest.approx(888 / nsa.steps_per_unit)
