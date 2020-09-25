# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.common.standard import move, mv, mvr, mvd, mvdr, rockit
from bliss.common import event


def test_mv(roby):
    mv(roby, 2)
    assert roby.position == pytest.approx(2)


def test_mvr(roby):
    p1 = roby.position
    mvr(roby, 1)
    assert roby.position == pytest.approx(p1 + 1)


def test_group_mv(roby, robz):
    mv(roby, 3, robz, 1)
    assert roby.position == pytest.approx(3)
    assert robz.position == pytest.approx(1)


def test_mvd(roby):
    roby.offset = 1
    mvd(roby, 2)
    assert roby.position == pytest.approx(3)
    assert roby.dial == pytest.approx(2)


def test_mvdr(roby):
    roby.offset = 1
    p1 = roby.dial
    p2 = roby.position
    mvdr(roby, 1)
    assert roby.dial == pytest.approx(p1 + 1)
    assert roby.position == pytest.approx(p2 + 1)


def test_group_mvd(roby, robz):
    roby.offset, robz.offset = 1, 2
    mvd(roby, 3, robz, 1)
    assert roby.dial == pytest.approx(3)
    assert robz.dial == pytest.approx(1)
    assert roby.position == pytest.approx(4)
    assert robz.position == pytest.approx(3)


def test_interrupted_mv(roby):
    mv_task = gevent.spawn(mv, roby, 1000)
    gevent.sleep(0.1)
    mv_task.kill()
    assert "READY" in roby.state
    assert roby.position == roby._set_position


def test_rockit(robz):
    mot_position = {"max": robz.position, "min": robz.position}
    synchro = gevent.event.Event()

    def listen_pos(pos):
        max_pos = mot_position.get("max")
        min_pos = mot_position.get("min")
        if max_pos is None or pos > max_pos:
            mot_position["max"] = pos
        if min_pos is None or pos < min_pos:
            mot_position["min"] = pos
        synchro.set()

    event.connect(robz, "position", listen_pos)

    current_pos = robz.position
    with gevent.Timeout(5):
        with rockit(robz, 1):
            while True:
                synchro.wait()
                synchro.clear()
                if (
                    abs((mot_position.get("max") - (current_pos + 1.0 / 2))) < 1e-6
                    and abs((mot_position.get("min") - (current_pos - 1.0 / 2))) < 1e-6
                ):
                    break
    event.disconnect(robz, "position", listen_pos)
    assert robz.position == pytest.approx(current_pos)
    assert mot_position.get("max") == pytest.approx(current_pos + 1 / 2)
    assert mot_position.get("min") == pytest.approx(current_pos - 1 / 2)


def test_move_std_func_no_wait_motor_stop(roby, robz):
    move(roby, 1e6, robz, 1e6, wait=False)

    assert "MOVING" in roby.state
    assert "MOVING" in robz.state

    with gevent.Timeout(1):
        roby.stop()

    assert "READY" in roby.state
    assert "READY" in robz.state
