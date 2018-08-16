# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.common.standard import Group
import sys

@pytest.fixture
def bad_motor(beacon):
    bad = beacon.get('bad')
    bad.controller.bad_start = False
    bad.controller.bad_state = False
    bad.controller.bad_state_after_start = False
    bad.controller.bad_stop = False
    bad.dial(0); bad.position(0)
    bad.sync_hard()
    yield bad

def test_bad_start(bad_motor):
    bad_motor.controller.bad_start = True

    with pytest.raises(RuntimeError):
        bad_motor.move(1)
    
    assert 'READY' in bad_motor.state()
    assert bad_motor.position() == 0

def test_bad_start_group(bad_motor, robz):
    grp = Group(bad_motor, robz)
    bad_motor.controller.bad_start = True

    with pytest.raises(RuntimeError):
       grp.move({ bad_motor: 1, robz: 2 })

    assert grp.state().READY
    assert bad_motor.position() == 0
    assert robz.position() < 0.2

def test_state_failure(bad_motor, monkeypatch):
    bad_motor.controller.bad_state_after_start = True

    infos = []
    monkeypatch.setattr(sys, "excepthook", lambda *info: infos.append(info))
    with pytest.raises(RuntimeError) as exc:
        bad_motor.move(1)
    state_index = bad_motor.controller.state_msg_index

    assert str(exc.value)=='BAD STATE 1'
    assert len(infos) == 2
    assert str(infos[0][1]) == 'BAD STATE %d' % (state_index-1)
    assert 'FAULT' in bad_motor.state()

    with pytest.raises(RuntimeError):
        bad_motor.state(read_hw=True)

    gevent.sleep(bad_motor.controller.state_recovery_delay)

    assert 'READY' in bad_motor.state(read_hw=True)

def test_stop_failure(bad_motor):
    bad_motor.controller.bad_stop = True

    bad_motor.move(1, wait=False)
    gevent.sleep(0.01)
   
    with pytest.raises(RuntimeError):
        bad_motor.stop()

    assert 'READY' in bad_motor.state()



