# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import numpy
from unittest import mock

from bliss.common import event
from bliss.common.standard import Group
from bliss.common.axis import AxisState


def test_group_move(robz, roby):
    robz_pos = robz.position
    roby_pos = roby.position
    grp = Group(robz, roby)

    assert grp.state.READY

    target_robz = robz_pos + 10
    target_roby = roby_pos + 10

    grp.move(robz, target_robz, roby, numpy.array([target_roby]), wait=False)

    assert grp.state.MOVING
    assert robz.state.MOVING
    assert roby.state.MOVING

    grp.wait_move()

    assert robz.state.READY
    assert roby.state.READY
    assert grp.state.READY


def test_stop(roby, robz):
    grp = Group(robz, roby)
    grp.move(robz, 1, roby, 1)

    assert robz.state.READY
    assert roby.state.READY
    assert grp.state.READY

    grp.move({robz: 0, roby: 0}, wait=False)
    assert grp.state.MOVING

    grp.stop()

    assert grp.state.READY
    assert robz.state.READY
    assert roby.state.READY

    # ensure motors are stopped (only valid for mockup, of course)
    assert robz.controller._get_axis_motion(robz) is None
    assert roby.controller._get_axis_motion(roby) is None


def test_ctrlc(roby, robz):
    grp = Group(robz, roby)
    assert robz.state.READY
    assert roby.state.READY
    assert grp.state.READY

    grp.move({robz: -10, roby: -10}, wait=False)

    gevent.sleep(0.01)

    grp._group_move._move_task.kill(KeyboardInterrupt, block=False)

    with pytest.raises(KeyboardInterrupt):
        grp.wait_move()

    assert grp.state.READY
    assert robz.state.READY
    assert grp.state.READY


def test_position_reading(beacon, robz, roby):
    grp = Group(robz, roby)
    positions_dict = grp.position

    for axis, axis_pos in positions_dict.items():
        group_axis = beacon.get(axis.name)
        assert axis == group_axis
        assert axis.position == axis_pos


def test_move_done(roby, robz):
    grp = Group(robz, roby)
    res = {"ok": False}

    def callback(move_done, res=res):
        if move_done:
            res["ok"] = True

    roby_pos = roby.position
    robz_pos = robz.position

    event.connect(grp, "move_done", callback)

    grp.rmove({robz: 2, roby: 3})

    assert res["ok"] == True
    assert robz.position == robz_pos + 2
    assert roby.position == roby_pos + 3

    event.disconnect(grp, "move_done", callback)


def test_hardlimits_set_pos(robz, robz2):
    assert robz._set_position == 0
    grp = Group(robz, robz2)
    robz.controller.set_hw_limits(robz, -2, 2)
    robz2.controller.set_hw_limits(robz2, -2, 2)
    with pytest.raises(RuntimeError):
        grp.move({robz: 3, robz2: 1})
    assert robz._set_position == robz.position


def test_no_move(robz):
    robz.move(0)
    grp = Group(robz)
    with gevent.Timeout(1):
        grp.move(robz, 0)
    assert not grp.is_moving


def test_is_moving_prop(robz, robz2):
    # issue #1599
    group = Group(robz, robz2)
    robz.move(10, wait=False, relative=True)
    assert robz.is_moving
    assert "MOVING" in group.state
    assert group.is_moving
    robz.stop()
    assert "READY" in group.state
    group.move(robz, 10, wait=False, relative=True)
    assert "MOVING" in group.state
    assert group.is_moving
    assert robz.is_moving
    assert not robz2.is_moving
    group.stop()


def test_no_hardware_access_if_at_pos(robz, roby):
    g = Group(roby, robz)

    g.move(roby, 1, robz, 2)

    # roby
    with mock.patch.object(
        roby.controller, "read_position", return_value=1. * roby.steps_per_unit
    ) as read_position:
        g.move(roby, 1, robz, 2)
        read_position.assert_not_called()

    with mock.patch.object(
        robz.controller, "state", return_value=AxisState("READY")
    ) as read_state:

        g.move(roby, 1, robz, 2)
        read_state.assert_not_called()

    # robz
    with mock.patch.object(
        robz.controller, "read_position", return_value=1. * robz.steps_per_unit
    ) as read_position:
        g.move(roby, 1, robz, 2)
        read_position.assert_not_called()

    with mock.patch.object(
        robz.controller, "state", return_value=AxisState("READY")
    ) as read_state:

        g.move(roby, 1, robz, 2)
        read_state.assert_not_called()
