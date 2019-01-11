# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

import pytest

from bliss.common.axis import Motion
from bliss.common.standard import Group
from bliss.controllers.motors.mockup import MockupHook


def test_config(hooked_m0, hooked_m1):
    """test hooked axes configuration"""
    assert len(hooked_m0.motion_hooks) == 1
    hook0 = hooked_m0.motion_hooks[0]
    assert hook0.name == "hook0"
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0

    assert len(hooked_m1.motion_hooks) == 2
    assert hook0 == hooked_m1.motion_hooks[0]
    hook1 = hooked_m1.motion_hooks[1]
    assert hook1.name == "hook1"
    assert hook1.nb_pre_move == 0
    assert hook1.nb_post_move == 0

    assert len(hook0.axes) == 3
    assert "hooked_m0" in hook0.axes
    assert "hooked_m1" in hook0.axes
    assert "hooked_error_m0" in hook0.axes

    assert len(hook1.axes) == 1
    assert "hooked_m1" in hook1.axes


def test_axis_move(hooked_m0):
    """test single motion hook works in single axis motion"""
    assert hooked_m0.state.READY

    hook0 = hooked_m0.motion_hooks[0]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0

    hooked_m0.move(180, wait=False)

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 0
    assert hooked_m0.state.MOVING
    assert len(hook0.last_pre_move_args) == 1
    assert isinstance(hook0.last_pre_move_args[0], Motion)

    hooked_m0.wait_move()

    assert hook0.last_post_move_args[-1].type == "move"
    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert hooked_m0.state.READY
    assert hooked_m0.position == 180
    assert hooked_m0._set_position == 180
    assert len(hook0.last_post_move_args) == 1
    assert isinstance(hook0.last_post_move_args[0], Motion)


def test_axis_homing(hooked_m0):
    hook0 = hooked_m0.motion_hooks[0]

    hooked_m0.home()

    assert hook0.last_post_move_args[-1].type == "homing"


def test_axis_limit(hooked_m0):
    hook0 = hooked_m0.motion_hooks[0]

    hooked_m0.controller.set_hw_limits(hooked_m0, -2, 2)
    hooked_m0.hw_limit(1)

    assert hook0.last_post_move_args[-1].type == "limit_search"


def test_axis_move2(hooked_m1):
    """test multiple motion hooks works in single axis motion"""
    assert hooked_m1.state.READY

    hook0 = hooked_m1.motion_hooks[0]
    hook1 = hooked_m1.motion_hooks[1]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0

    hooked_m1.move(180, wait=False)

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 0
    assert hooked_m1.state.MOVING

    hooked_m1.wait_move()

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 1
    assert hooked_m1.state.READY
    assert hooked_m1.position == 180
    assert hooked_m1._set_position == 180


def test_axis_multiple_move(hooked_m0):
    """test single motion hook works in multiple single axis motion"""
    hook0 = hooked_m0.motion_hooks[0]

    for i in range(100):
        assert hooked_m0.state.READY
        assert hook0.nb_pre_move == i
        assert hook0.nb_post_move == i
        hooked_m0.move((i + 1) * 2, wait=False)
        assert hook0.nb_pre_move == i + 1
        assert hook0.nb_post_move == i
        assert hooked_m0.state.MOVING
        hooked_m0.wait_move()
        assert hook0.nb_pre_move == i + 1
        assert hook0.nb_post_move == i + 1
        assert hooked_m0.state.READY


def test_stop(hooked_m0):
    """test motion hooks work when motor is stopped during motion"""
    assert hooked_m0.state.READY

    hook0 = hooked_m0.motion_hooks[0]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0

    hooked_m0.move(180, wait=False)

    assert hooked_m0._set_position == 180

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 0
    assert hooked_m0.state.MOVING

    hooked_m0.stop()

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert hooked_m0.state.READY


def test_error_hook(hooked_error_m0):
    """test a hook which generates error on pre_move"""
    assert hooked_error_m0.state.READY

    hook0 = hooked_error_m0.motion_hooks[0]
    hook1 = hooked_error_m0.motion_hooks[1]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 0
    assert hook1.nb_post_move == 0

    with pytest.raises(MockupHook.Error):
        hooked_error_m0.move(180, wait=False)

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 0
    assert hook1.nb_post_move == 0
    assert hooked_error_m0.state.READY


def test_group_move(hooked_m0, hooked_m1):
    """test hook with group movement"""
    hooked_m0_pos = hooked_m0.position
    hooked_m1_pos = hooked_m1.position
    hook0 = hooked_m1.motion_hooks[0]
    hook1 = hooked_m1.motion_hooks[1]

    grp = Group(hooked_m0, hooked_m1)

    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 0
    assert hook1.nb_post_move == 0
    assert grp.state.READY

    target_hooked_m0 = hooked_m0_pos + 50
    target_hooked_m1 = hooked_m1_pos + 50

    grp.move(hooked_m0, target_hooked_m0, hooked_m1, target_hooked_m1, wait=False)

    assert hook0.nb_pre_move == 2
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 0
    assert len(hook0.last_pre_move_args) == 1
    assert isinstance(hook0.last_pre_move_args[0], Motion)
    assert len(hook1.last_pre_move_args) == 1
    assert isinstance(hook1.last_pre_move_args[0], Motion)
    assert grp.state.MOVING

    grp.wait_move()

    assert hook0.nb_pre_move == 2
    assert hook0.nb_post_move == 2
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 1
    assert len(hook0.last_post_move_args) == 1
    assert isinstance(hook0.last_post_move_args[0], Motion)
    assert len(hook1.last_post_move_args) == 1
    assert isinstance(hook1.last_post_move_args[0], Motion)
    assert hooked_m0.state.READY
    assert hooked_m1.state.READY
    assert grp.state.READY


def test_group_stop(hooked_m0, hooked_m1):
    """test group motion software stop with hooks"""
    hook0 = hooked_m1.motion_hooks[0]
    hook1 = hooked_m1.motion_hooks[1]

    grp = Group(hooked_m0, hooked_m1)
    grp.move(hooked_m0, 1, hooked_m1, 1)

    assert hook0.nb_pre_move == 2
    assert hook0.nb_post_move == 2
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 1
    assert hooked_m0.state.READY
    assert hooked_m1.state.READY
    assert grp.state.READY

    grp.move({hooked_m0: 0, hooked_m1: 0}, wait=False)

    assert hook0.nb_pre_move == 4
    assert hook0.nb_post_move == 2
    assert hook1.nb_pre_move == 2
    assert hook1.nb_post_move == 1
    assert grp.state.MOVING

    grp.stop()

    assert hook0.nb_pre_move == 4
    assert hook0.nb_post_move == 4
    assert hook1.nb_pre_move == 2
    assert hook1.nb_post_move == 2
    assert grp.state.READY
    assert hooked_m0.state.READY
    assert hooked_m1.state.READY
