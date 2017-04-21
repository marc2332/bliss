# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
from bliss.common import event
from bliss.common.standard import Group

@pytest.fixture
def robz(beacon):
  m = beacon.get("robz")
  #m.sync_hard()
  yield m
  m.apply_config()

@pytest.fixture
def roby(beacon):
  m = beacon.get("roby")
  #m.sync_hard()
  yield m
  m.apply_config()

@pytest.fixture
def robz2(beacon):
  m = beacon.get("robz2")
  #m.sync_hard()
  yield m
  m.apply_config()

def test_group_move(robz, roby):
    robz_pos = robz.position()
    roby_pos = roby.position()
    grp = Group(robz, roby)

    assert grp.state() == "READY"

    target_robz = robz_pos + 50
    target_roby = roby_pos + 50

    grp.move(robz, target_robz, roby, target_roby, wait=False)

    assert grp.state() == "MOVING"
    #assert robz.state() == "MOVING"
    #assert roby.state() == "MOVING"

    grp.wait_move()
    robz.wait_move()
    roby.wait_move()

    assert robz.state() == "READY"
    assert roby.state() == "READY"
    assert grp.state() == "READY"

def test_stop(roby, robz):
    grp = Group(robz, roby)
    assert robz.state() == "READY"
    assert roby.state() == "READY"
    assert grp.state() == "READY"
    import pdb;pdb.set_trace()
    grp.move({robz: 0, roby: 0}, wait=False)
    assert grp.state() == "MOVING"

    grp.stop()

    assert grp.state() == "READY"
    assert robz.state() == "READY"
    assert grp.state() == "READY"

"""
def test_ctrlc(roby, robz):
    grp = Group(robz, roby)
    assert robz.state() == "READY"
    assert roby.state() == "READY"
    assert grp.state() == "READY"
    grp.move({robz: -10, roby: -10}, wait=False)
    
    time.sleep(0.01)
    
    grp._Group__move_task.kill(KeyboardInterrupt, block=False)

    with pytest.raises(KeyboardInterrupt):
        grp.wait_move()

    assert grp.state() == "READY"
    assert robz.state() == "READY"
    assert grp.state() == "READY"
"""

def test_position_reading(beacon, robz, roby):
    grp = Group(robz, roby)
    positions_dict = grp.position()

    for axis, axis_pos in positions_dict.iteritems():
        group_axis = beacon.get(axis.name)
        assert axis == group_axis
        assert axis.position() == axis_pos
    
def test_move_done(roby, robz):
    grp = Group(robz, roby)
    res = {"ok": False}

    def callback(move_done, res=res):
        if move_done:
            res["ok"] = True

    roby_pos = roby.position()
    robz_pos = robz.position()

    event.connect(grp, "move_done", callback)

    grp.rmove({robz: 2, roby: 3})

    assert res["ok"] == True
    assert robz.position() == robz_pos+2
    assert roby.position() == roby_pos+3

""" 
def test_bad_startone(roby, robz):
    grp = Group(robz, roby)
    roby.dial(0); roby.position(0)
    robz.dial(0); robz.position(0)

    try:
        roby.controller.set_error(True)
        with pytest.raises(RuntimeError):
           grp.move({ robz: 1, roby: 2 })
        assert grp.state() == 'READY'
        assert roby.position() == 0
        assert robz.position() == 0
    finally:
        roby.controller.set_error(False)

def test_bad_startall(robz, robz2):
    # robz and robz2 are on the same controller
    robz.dial(0); robz.position(0)
    robz2.dial(0); robz2.position(0)
    grp = Group(robz, robz2)

    try:
        robz.controller.set_error(True)
        with pytest.raises(RuntimeError):
           grp.move({ robz: 1, robz2: 2 })
        assert grp.state() == 'READY'
        assert robz.position() == 0
        assert robz2.position() == 0
    finally:
        robz.controller.set_error(False) 

def test_hardlimits_set_pos(robz, robz2):
    robz.dial(0); robz.position(0)
    robz2.dial(0); robz2.position(0)
    assert robz._set_position() == 0
    grp = Group(robz, robz2)
    robz.controller.set_hw_limit(robz,-2,2)
    robz2.controller.set_hw_limit(robz2,-2,2)
    with pytest.raises(RuntimeError):
        grp.move({robz:3,robz2:1})
    assert robz._set_position() == robz.position()
"""      

def test_hw_control(robz, robz2):
    robz.dial(0); robz.position(0)
    robz2.dial(0); robz2.position(0)
    grp = Group(robz, robz2)
    grp.move({ robz: 2, robz2: 2 }, wait=False)
    assert robz._hw_control == True
    assert robz2._hw_control == True
    grp.wait_move()
    assert robz._hw_control == False
    assert robz2._hw_control == False


