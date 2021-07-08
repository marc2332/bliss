# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
import sys
import math
from bliss.common.standard import Group
from bliss.common.standard import sync
from bliss.common import event
from bliss.common.axis import AxisFaultError


def test_position_reading_delay(bad_motor):
    with gevent.Timeout(0.5):
        # read "hardware"
        bad_motor._hw_position
    bad_motor.controller.position_reading_delay = 1
    with pytest.raises(gevent.Timeout):
        with gevent.Timeout(0.5):
            # read "hardware"
            bad_motor._hw_position


def test_bad_start(bad_motor):
    bad_motor.controller.bad_start = True

    with pytest.raises(RuntimeError):
        bad_motor.move(1)

    assert "READY" in bad_motor.state
    assert bad_motor.position == 0


@pytest.mark.flaky(reruns=3, reason="issue2353")
def test_bad_start_group(bad_motor, robz):
    grp = Group(bad_motor, robz)
    bad_motor.controller.bad_start = True

    with pytest.raises(RuntimeError):
        grp.move({bad_motor: 1, robz: 2})

    assert grp.state.READY
    assert bad_motor.position == 0
    assert robz.position < 0.2


def test_state_failure(bad_motor, monkeypatch):
    bad_motor.controller.bad_state_after_start = True

    infos = []
    monkeypatch.setattr(sys, "excepthook", lambda *info: infos.append(info))
    with pytest.raises(RuntimeError) as exc:
        bad_motor.move(1)
    state_index = bad_motor.controller.state_msg_index

    assert str(exc.value) == "BAD STATE 1"
    assert len(infos) == 1
    assert str(infos[0][1]) == "BAD STATE %d" % state_index
    assert "FAULT" in bad_motor.state

    with pytest.raises(RuntimeError):
        bad_motor.hw_state

    gevent.sleep(bad_motor.controller.state_recovery_delay)

    assert "READY" in bad_motor.hw_state


def test_stop_failure(bad_motor):
    bad_motor.controller.bad_stop = True

    bad_motor.move(1, wait=False)
    gevent.sleep(0.01)

    with pytest.raises(RuntimeError):
        bad_motor.stop()

    assert "READY" in bad_motor.state


def test_encoder_init_failure(bad_motor, capsys):
    """
    Ensure exception in encoder initialization is not hidden
    cf. issue #2853
    """
    bad_motor.controller.bad_encoder = True

    bad_motor.__info__()

    assert "ZeroDivisionError" in capsys.readouterr().err


def test_state_after_bad_move(bad_motor):
    # related to issue #788
    try:
        g = gevent.spawn_later(0.1, setattr, bad_motor.controller, "bad_position", True)
        with pytest.raises(RuntimeError):
            bad_motor.move(1)

        g.get()
    finally:
        # make sure there is no dangling greenlet
        g.kill()

    assert "FAULT" in bad_motor.state


def test_nan_position(bad_motor):
    assert bad_motor.position == 0  # initial pos

    bad_motor.offset = 1

    # this configures the controller to return
    # nan position
    bad_motor.controller.nan_position = True

    assert math.isnan(bad_motor.position)
    # the set position is the same as before
    assert bad_motor._set_position == 1
    # check offset has changed
    assert bad_motor.offset == 1

    # change offset => pos is nan but it should work
    bad_motor.offset = 2
    assert bad_motor.offset == 2

    # try to assign a new user position => should calc offset,
    # but as current pos is nan it will do nothing
    bad_motor.position = -1
    assert math.isnan(bad_motor.position)
    assert bad_motor.offset == 2

    bad_motor.controller.nan_position = False
    bad_motor.sync_hard()

    assert bad_motor.position == 2

    bad_motor.dial = float("nan")
    assert math.isnan(bad_motor.position)
    assert bad_motor.offset == 2
    assert bad_motor._set_position == 2


def test_bad_sync_hard(bad_motor, roby, capsys):
    bad_motor.controller.bad_position = True
    sync_hard_called = False

    def cb():
        nonlocal sync_hard_called
        sync_hard_called = True

    event.connect(roby, "sync_hard", cb)

    sync(bad_motor, roby)

    assert sync_hard_called
    assert f"axis '{bad_motor.name}'" in capsys.readouterr().err


def test_issue_1719(bad_motor, capsys):
    bad_motor.move(1000, wait=False)

    gevent.sleep(bad_motor.acctime)

    bad_motor.controller.bad_position_only_once = True

    try:
        bad_motor.wait_move()
    except Exception:
        pass

    assert (
        not "TypeError: '<=' not supported between instances of 'NoneType' and 'int'"
        in capsys.readouterr().err
    )


def test_fault_state(bad_motor):
    bad_motor.controller.bad_encoder = False
    bad_motor.move(1000, wait=False)

    gevent.sleep(bad_motor.acctime)

    bad_motor.controller.fault_state = True

    with pytest.raises(AxisFaultError) as excinfo:
        bad_motor.wait_move()

    assert bad_motor.name in str(excinfo.value)
    bad_motor.controller.fault_state = False

    bad_motor.move(0)
    # assert "READY" in bad_motor.state
