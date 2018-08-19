# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
from bliss.common import event
from bliss.common.axis import Modulo

def test_property_setting(robz):
    assert robz.velocity() == 100

def test_controller_from_axis(robz):
    assert robz.controller.name == "test"

def test_state_callback(robz):
    ready_event = gevent.event.AsyncResult()
    def callback(state):
      ready_event.set(state.READY)

    event.connect(robz, "state", callback)

    robz.rmove(1)

    assert ready_event.get(timeout=0.1)
    assert robz.state().READY

def test_move_done_callback(robz):
    ready_event = gevent.event.AsyncResult()
    dial_event = gevent.event.AsyncResult()

    def callback(move_done):
        if move_done:
            ready_event.set(robz.is_moving is False)
            dial_event.set(robz.dial())

    event.connect(robz, "move_done", callback)

    robz.rmove(1)

    assert ready_event.get(timeout=0.1)
    assert dial_event.get() == 1

    event.disconnect(robz, "move_done", callback)


def test_position_callback(robz):
    storage={"last_pos":None, "last_dial_pos":None}
    def callback(pos, old=storage):
        old["last_pos"]=pos
    def dial_callback(pos,old=storage):
        old["last_dial_pos"]=pos

    event.connect(robz, "position", callback)
    event.connect(robz, "dial_position", dial_callback)

    robz.position(1)
    pos = robz.position()
    robz.rmove(1)
    assert storage["last_pos"] == pytest.approx(pos+1)
    assert storage["last_dial_pos"] == pytest.approx(robz.user2dial(pos+1))

def test_rmove(robz):
    robz.move(0)
    assert robz.position() == pytest.approx(0)
    robz.rmove(0.1)
    robz.rmove(0.1)
    assert robz.position() == pytest.approx(0.2)

def test_acceleration(robz):
    acc = robz.acceleration()

    assert robz.acctime() == pytest.approx(robz.velocity()/robz.acceleration())

    v = robz.velocity()/2.0
    robz.velocity(v)

    assert robz.acceleration() == acc
    assert robz.acctime() == v/acc

    robz.acctime(0.03)
    assert robz.acceleration() == v/0.03

    assert robz.acceleration(from_config=True) == 300

def test_axis_set_acctime(roby):
    acc = 0.250
    assert roby.acctime(acc) == acc

def test_axis_move(robz):
    assert robz.state().READY

    robz.move(180, wait=False)

    assert robz.state().MOVING

    robz.wait_move()

    assert robz.state().READY

    assert robz.position() == 180
    assert robz._set_position() == 180

def test_axis_multiple_move(robz):
    robz.velocity(1000)
    robz.acceleration(10000)
    for i in range(10):
        assert robz.state().READY
        robz.move((i+1)*2, wait=False)
        assert robz.state().MOVING
        robz.wait_move()
        assert robz.state().READY

def test_axis_init(robz):
    assert robz.state().READY
    assert robz.settings.get("init_count") == 1


def test_stop(robz):
    assert robz.state().READY

    robz.move(180, wait=False)

    assert robz._set_position() == 180

    assert robz.state().MOVING

    robz.stop()

    assert robz.state().READY

def test_asynchronous_stop(robz):
    robz.velocity(1)

    robz.move(180, wait=False)

    assert robz.state().MOVING

    started_time = time.time()
    time.sleep(1+robz.acctime())

    robz.stop(wait=False)

    elapsed_time = time.time() - started_time
    assert robz.state().MOVING

    robz.wait_move()

    assert robz.state().READY

    assert robz.position() == pytest.approx(elapsed_time+robz.acceleration()*robz.acctime()**2, 1e-2)

def test_home_stop(robz):
    robz.home(wait=False)

    time.sleep(0.1)

    assert robz.state().MOVING

    robz.stop()

    robz.wait_move()

    assert robz.state().READY

def test_limit_search_stop(robz):
    robz.controller.set_hw_limits(robz, -5, 5)
    robz.hw_limit(1, wait=False)

    time.sleep(0.1)

    assert robz.state().MOVING

    robz.stop()

    robz.wait_move()

    assert robz.state().READY

def test_limits(robz):
    iset_pos = robz._set_position()
    robz.limits(-1, 1)
    assert robz.limits() == (-1, 1)
    with pytest.raises(ValueError):
        robz.move(1.1)
    assert robz._set_position() == iset_pos
    with pytest.raises(ValueError):
        robz.move(-1.1)
    assert robz._set_position() == iset_pos
    robz.limits(-2.1, 1.1)
    robz.rmove(1)
    robz.rmove(-2)
    assert robz.state().READY

def test_limits2(robz, roby):
    iset_pos = robz._set_position()
    assert robz.limits() == (-1000,1E9)
    assert roby.limits() == (float('-inf'),float('+inf'))
    with pytest.raises(ValueError):
        robz.move(-1001)
    assert robz._set_position() == iset_pos

def test_limits3(robz):
    robz.limits(-10,10)
    robz.position(10)
    assert robz.limits() == (0,20)
    assert robz._set_position() == 10

def test_backlash(roby):
    roby.move(-10, wait=False)

    assert roby.backlash_move == -12

    roby.wait_move()

    assert roby.position() == -10

    roby.move(-9)

    roby.limits(-11, 10)

    with pytest.raises(ValueError):
        roby.move(-10)

def test_backlash2(roby):
    roby.move(10, wait=False)
    assert roby.backlash_move == 0
    roby.wait_move()
    assert roby.position() == 10

def test_backlash3(roby):
    roby.position(1)
    assert roby.position() == 1

    roby.move(1, wait=False)

    assert roby.backlash_move == 0

    assert roby.state().READY

def test_backlash_stop(roby):
    roby.move(-10,wait=False)
    assert roby.backlash_move == -12
    time.sleep(0.1)
    pos = roby.position()
    roby.stop()
    assert pytest.approx(roby.position(), pos, 1e-3)
    assert pytest.approx(roby._set_position(), pos, 1e-3)
    assert roby.state().READY

def test_axis_steps_per_unit(roby):
    roby.move(180, wait=False)
    roby.wait_move()
    assert roby.target_pos == roby.steps_per_unit * 180

def test_axis_set_pos(roby):
     roby.position(10)
     assert roby.position(10) == pytest.approx(10)
     ipos = roby.position()
     fpos = 10
     ilow_lim, ihigh_lim = roby.limits(-100, 100)
     roby.position(fpos)
     assert roby.position(fpos) == pytest.approx(fpos)
     assert roby._set_position() == pytest.approx(fpos)
     dpos = fpos - ipos
     flow_lim, fhigh_lim = roby.limits()
     dlow_lim, dhigh_lim = flow_lim - ilow_lim, fhigh_lim - ihigh_lim
     assert dlow_lim == pytest.approx(dpos)
     assert dhigh_lim == pytest.approx(dpos)

def test_axis_set_velocity(roby):
    # vel is in user-unit per seconds.
    assert roby.velocity(5000) == 5000
    assert roby.velocity(from_config=True) == 2500

def test_custom_method(roby):
    roby.Set_Closed_Loop(True)
    roby.Set_Closed_Loop(False)
    roby.Set_Closed_Loop()

def test_home_search(roby):
    roby.home(wait=False)
    assert roby.state().MOVING
    roby.wait_move()
    assert roby.state().READY
    roby.dial(38930)
    roby.position(38930)
    assert roby.offset == 0
    assert roby.position() == 38930

def test_ctrlc(robz):
    robz.move(100, wait=False)
    assert robz.state().MOVING
    assert robz.is_moving
    time.sleep(0.1)
    robz._group_move._move_task.kill(KeyboardInterrupt, block=False)
    with pytest.raises(KeyboardInterrupt):
        robz.wait_move()
    assert not robz.is_moving
    assert robz.state().READY
    assert robz.position() < 100

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
        assert robz.state().MOVING
        with pytest.raises(Exception) as e:
            robz.move(-10)
        assert 'MOVING' in str(e)
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
    assert 'OFF' in robz.state()
    robz.on()
    assert 'READY' in robz.state()


def test_on_off(robz):
    robz.off()
    assert robz.state().OFF
    with pytest.raises(RuntimeError):
        robz.move(1)
    robz.on()
    assert robz.state().READY
    robz.move(1)
    assert robz.position() == pytest.approx(1)
    robz.move(2, wait=False)
    with pytest.raises(RuntimeError):
        robz.off()
    robz.wait_move()
    robz.off()
    assert robz.state().OFF

def test_dial(robz):
    robz.position(1)
    assert robz.dial() == 0
    assert robz.position() == 1
    robz.position(robz.dial())
    assert robz.position() == 0
    robz.dial(1)
    assert robz.dial() == 1
    assert robz.position() == 0
    robz.position(robz.dial(2))
    assert robz.dial() == 2
    assert robz.position() == 2

def test_limit_search(robz):
    robz.controller.set_hw_limits(robz, -11.5, 12.4)
    robz.hw_limit(1)
    assert robz.dial() == 12.4
    robz.hw_limit(-1)
    assert robz.dial() == -11.5

def test_set_position(m0):
    assert m0.steps_per_unit == 1
    assert m0.position() == m0._set_position()
    m0.rmove(0.1)
    assert m0._set_position() == 0.1
    for i in range(9):
        m0.rmove(0.1)
    assert m0._set_position() == pytest.approx(1.0)
    assert m0.position() == pytest.approx(m0._set_position())
    m0.move(0.4)
    assert m0._set_position() == 0.4
    assert m0.position() == 0
    m0.rmove(0.6)
    assert m0._set_position() == 1
    assert m0.position() == m0._set_position()
    m0.move(2, wait=False)
    time.sleep(0.01)
    m0._group_move._move_task.kill(KeyboardInterrupt, block=False)
    try:
        m0.wait_move()
    except KeyboardInterrupt:
        pass
    m0.move(1)
    assert m0._set_position() == 1

def test_interrupted_waitmove(m0):
    m0.move(100,wait=False)
    waitmove = gevent.spawn(m0.wait_move)
    time.sleep(0.01)
    with pytest.raises(KeyboardInterrupt):
        kill_pos = m0.position()
        waitmove.kill(KeyboardInterrupt)
    time.sleep(0.1)
    assert m0.position() == pytest.approx(kill_pos)
    assert m0.state().READY

def test_hardware_limits(roby):
    try:
        roby.controller.set_hw_limits(roby, -2,2)
        with pytest.raises(RuntimeError):
            roby.move(3)

        assert roby.position() == 2

        # move hit limit because of backlash
        with pytest.raises(RuntimeError):
            roby.move(0)
        roby.move(1)

        assert roby.position() == 1
        with pytest.raises(RuntimeError):
            roby.move(-3)

        assert roby.position() == -2
    finally:
        roby.controller.set_hw_limits(roby, None, None)


def test_no_offset(roby):
    try:
        roby.no_offset = True
        roby.move(0)
        roby.position(1)
        assert roby.dial() == 1
        roby.dial(0)
        assert roby.position() == 0
    finally:
        roby.no_offset = False

def test_settings_to_config(roby):
    roby.velocity(3)
    roby.acceleration(10)
    roby.limits(None, None)
    assert roby.velocity(from_config=True) == 2500
    assert roby.acceleration(from_config=True) == 1000
    roby.settings_to_config()
    assert roby.velocity(from_config=True) == 3
    assert roby.acceleration(from_config=True) == 10
    roby.velocity(2500)
    roby.acceleration(1000)
    roby.settings_to_config()

def test_apply_config(roby):
    roby.velocity(1)
    roby.acceleration(2)
    roby.limits(0,10)
    roby.apply_config()
    assert roby.velocity() == 2500
    assert roby.acceleration() == 1000
    assert roby.limits() == (float('-inf'), float('+inf'))

def test_jog(robz):
    robz.velocity(10)
    robz.jog(300)
    assert robz.velocity() == 300
    t = 1+robz.acctime()
    start_time = time.time()
    time.sleep(t)
    hw_position = robz._hw_position()
    elapsed_time = (time.time()-start_time) - robz.acctime()
    assert hw_position == pytest.approx(300*elapsed_time+robz.acceleration()*0.5*robz.acctime()**2, 1e-2)
    assert robz.state().MOVING
    robz.stop()
    assert robz.stop_jog_called
    assert robz.state().READY
    assert robz._set_position() == robz.position()
    robz.dial(0); robz.position(0)
    assert robz.velocity() == 10
    robz.jog(-300, reset_position=0)
    assert robz.velocity() == 300
    start_time = time.time()
    time.sleep(t)
    hw_position = robz._hw_position()
    elapsed_time = (time.time()-start_time) - robz.acctime()
    assert hw_position == pytest.approx(-300*elapsed_time-robz.acceleration()*0.5*robz.acctime()**2, 1e-2)
    robz.stop()
    assert robz.dial() == 0
    assert robz.velocity() == 10
    robz.jog(300, reset_position=Modulo())
    time.sleep(t)
    robz.stop()
    assert robz.position() == pytest.approx(90, 0.1)

def test_jog2(jogger):
    jogger.jog(300) #this should go in the opposite direction because steps_per_unit < 0
    t = 1+jogger.acctime()
    start_time = time.time()
    time.sleep(t)
    hw_position = jogger._hw_position()
    elapsed_time = (time.time()-start_time) - jogger.acctime()
    assert hw_position == pytest.approx(300*elapsed_time+jogger.acceleration()*0.5*jogger.acctime()**2, 1e-2)
    jogger.stop()

def test_measured_position(m1, roby):
    assert m1.measured_position() == m1.position()
    with pytest.raises(RuntimeError):
      roby.measured_position()
