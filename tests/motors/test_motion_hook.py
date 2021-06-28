# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.common.axis import Motion
from bliss.common.standard import Group, mvr, ascan, d2scan
from bliss.scanning.scan import ScanState
from bliss.controllers.motors.mockup import Mockup, MockupHook
from bliss.common.hook import MotionHook
from bliss.config.static import ConfigNode


def test_motion_hook_init(beacon):
    class MyMotionHook(MotionHook):
        def init(self):
            self.init_called += 1
            for axis_name, axis in self.axes.items():
                assert axis.config.get("name") == axis.name
                assert axis.acceleration
                assert axis.velocity
                assert axis.position == 1

    hook = MyMotionHook()
    config_node = ConfigNode(beacon.root)
    config_node.update(
        {"name": "test_mh", "velocity": 100, "acceleration": 10, "steps_per_unit": 500}
    )
    config_node = config_node.to_dict()
    config_node["motion_hooks"] = [hook]

    cfg = {"axes": [config_node]}
    mockup_controller = Mockup(cfg)
    mockup_controller._initialize_config()

    test_mh = None

    try:
        test_mh = mockup_controller.get_axis("test_mh")
        test_mh.position = 1
        test_mh.motion_hooks[0].init_called = 0
        test_mh.move(1.1)
        test_mh.move(1.2)
        assert test_mh.motion_hooks[0].init_called == 1
    finally:
        if test_mh:
            test_mh.__close__()


def test_config(hooked_m0, hooked_error_m0, hooked_m1):
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


def test_axis_single_motion_hook_for_multiple_axes(hooked_m0, hooked_m1):
    """test single motion hook works with multiple axes motion"""
    assert hooked_m0.state.READY

    hook0 = hooked_m0.motion_hooks[0]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0

    mvr(hooked_m0, 1, hooked_m1, 2)

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert len(hook0.last_pre_move_args) == 2
    assert isinstance(hook0.last_pre_move_args[0], Motion)
    assert isinstance(hook0.last_pre_move_args[1], Motion)


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


def test_axis_single_motion_hook_multiple_move(hooked_m0):
    """test single motion hook works in multiple single axis motion"""
    hook0 = hooked_m0.motion_hooks[0]

    for i in range(3):
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


def test_pre_move_error(hooked_error_m0, capsys):
    """test a hook which generates error on pre_move"""
    assert hooked_error_m0.state.READY

    hook0 = hooked_error_m0.motion_hooks[0]
    hook1 = hooked_error_m0.motion_hooks[1]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 0
    assert hook1.nb_post_move == 0

    with pytest.raises(MockupHook.Error) as exc:
        hooked_error_m0.move(180, wait=False)
    assert "pre_move" in str(exc.value)

    output = capsys.readouterr().out.split("\n")
    assert output[0] == hook0.name + " in pre_move hook"
    assert output[1] == hook1.name + " in pre_move hook"
    assert output[2] == hook1.name + " in post_move hook"
    assert output[3] == hook0.name + " in post_move hook"
    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert hook1.nb_pre_move == 0  # hook failed to execute
    assert hook1.nb_post_move == 1  # still, post move is executed
    assert hooked_error_m0.state.READY

    # test for issue 1779
    assert hooked_error_m0._set_position == 0


def test_post_move_error(hooked_error_m1, capsys):
    """test a hook which generates error on post_move"""
    assert hooked_error_m1.state.READY

    hook0 = hooked_error_m1.motion_hooks[0]
    hook1 = hooked_error_m1.motion_hooks[1]
    assert hook0.nb_pre_move == 0
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 0
    assert hook1.nb_post_move == 0

    with pytest.raises(MockupHook.Error) as exc:
        hooked_error_m1.move(1)
    assert "post_move" in str(exc.value)

    # hooks are executed in reverse order,
    # so there would be hook1 post_move before
    # hook0 post_move
    output = capsys.readouterr().out.split("\n")
    assert output[0] == hook0.name + " in pre_move hook"
    assert output[1] == hook1.name + " in pre_move hook"
    assert output[2] == hook1.name + " in post_move hook"
    assert output[3] == hook0.name + " in post_move hook"
    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1  # check that post move is executed
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 0  # post_move could not execute
    assert hooked_error_m1.state.READY

    # check that _set_pos is ok if motion hook fails after move
    assert hooked_error_m1._set_position == 1


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

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 0
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 0
    assert [m.axis for m in hook0.last_pre_move_args if isinstance(m, Motion)] == [
        hooked_m0,
        hooked_m1,
    ]
    assert [m.axis for m in hook1.last_pre_move_args if isinstance(m, Motion)] == [
        hooked_m1
    ]
    assert grp.state.MOVING

    grp.wait_move()

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 1
    assert [m.axis for m in hook0.last_post_move_args if isinstance(m, Motion)] == [
        hooked_m0,
        hooked_m1,
    ]
    assert [m.axis for m in hook1.last_post_move_args if isinstance(m, Motion)] == [
        hooked_m1
    ]
    assert hooked_m0.state.READY
    assert hooked_m1.state.READY
    assert grp.state.READY


def test_group_stop(hooked_m0, hooked_m1):
    """test group motion software stop with hooks"""
    hook0 = hooked_m1.motion_hooks[0]
    hook1 = hooked_m1.motion_hooks[1]

    grp = Group(hooked_m0, hooked_m1)
    grp.move(hooked_m0, 1, hooked_m1, 1)

    assert hook0.nb_pre_move == 1
    assert hook0.nb_post_move == 1
    assert hook1.nb_pre_move == 1
    assert hook1.nb_post_move == 1
    assert hooked_m0.state.READY
    assert hooked_m1.state.READY
    assert grp.state.READY

    grp.move({hooked_m0: 0, hooked_m1: 0}, wait=False)

    assert hook0.nb_pre_move == 2
    assert hook0.nb_post_move == 1
    assert hook1.nb_pre_move == 2
    assert hook1.nb_post_move == 1
    assert grp.state.MOVING

    grp.stop()

    assert hook0.nb_pre_move == 2
    assert hook0.nb_post_move == 2
    assert hook1.nb_pre_move == 2
    assert hook1.nb_post_move == 2
    assert grp.state.READY
    assert hooked_m0.state.READY
    assert hooked_m1.state.READY


class MyMotionHook(MotionHook):
    def __init__(self, *args, **kwargs):
        self._post_move_called = 0
        super().__init__(*args, **kwargs)

    def post_move(self, motion_list):
        self._post_move_called += 1


def test_check_ready_exception(hooked_m0):
    hook = MyMotionHook()

    def _check_ready():
        raise RuntimeError

    hooked_m0._check_ready = _check_ready
    hooked_m0.motion_hooks.append(hook)
    assert hook._post_move_called == 0
    with pytest.raises(RuntimeError):
        hooked_m0.move(1)
    assert hook._post_move_called == 1

    # test for issue 1779
    assert hooked_m0._set_position == 0


class MyScanHook(MotionHook):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pre_scan_called = 0
        self._post_scan_called = 0
        self._pre_scan_axes = []
        self._post_scan_axes = []
        self._raise_exception = 0  # 1: in pre_scan, 2: in post_scan

    def pre_scan(self, axes):
        self._pre_scan_called += 1
        self._pre_scan_axes = [axis.name for axis in axes]
        if self._raise_exception == 1:
            raise RuntimeError("Exception in pre scan")

    def post_scan(self, axes):
        self._post_scan_called += 1
        self._post_scan_axes = [axis.name for axis in axes]
        if self._raise_exception == 2:
            raise RuntimeError("Exception in post scan")


def test_prescan_postscan(default_session, roby, robz, s1vg, s1u):
    diode = default_session.config.get("diode")
    hook = MyScanHook()

    roby.motion_hooks.append(hook)
    robz.motion_hooks.append(hook)

    ascan(roby, 0, 1, 3, 0.1, diode)

    assert hook._pre_scan_called == 1
    assert roby.name in hook._pre_scan_axes
    assert hook._post_scan_called == 1
    assert roby.name in hook._post_scan_axes
    hook._pre_scan_axes.clear()
    hook._post_scan_axes.clear()

    d2scan(roby, 0, 1, robz, 0, 1, 3, 0.1, diode)

    assert hook._pre_scan_called == 2
    assert roby.name in hook._pre_scan_axes
    assert robz.name in hook._pre_scan_axes
    assert hook._post_scan_called == 2
    assert roby.name in hook._post_scan_axes
    assert robz.name in hook._post_scan_axes
    hook._pre_scan_axes.clear()
    hook._post_scan_axes.clear()

    d2scan(roby, 0, 1, s1vg, 0, 1, 3, 0.1, diode)
    assert s1vg.name in hook._pre_scan_axes
    for s1vg_real_axis in s1vg.controller.reals:
        assert s1vg_real_axis.name in hook._post_scan_axes

    hook2 = MyScanHook()
    s1u.motion_hooks.append(hook2)
    hook2._raise_exception = 1

    s = d2scan(roby, 0, 1, s1vg, 0, 1, 3, 0.1, diode, run=False)
    with pytest.raises(RuntimeError):
        s.run()
    assert hook._pre_scan_called == 4
    assert hook._post_scan_called == 4
    assert hook2._pre_scan_called == 1
    assert hook2._post_scan_called == 1
    assert s.state == ScanState.KILLED  # scan is killed because it failed in "prepare"

    hook2._raise_exception = 0
    hook3 = MyScanHook()
    s1vg.motion_hooks.append(hook3)
    hook3._raise_exception = 2
    roby_pos = roby.position
    s1vg_pos = s1vg.position
    s = d2scan(roby, 0, 1, s1vg, 0, 1, 3, 0.1, diode, run=False)
    with pytest.raises(RuntimeError):
        s.run()
    assert s.state == ScanState.DONE  # scan is done because it failed in finalization
    assert hook._pre_scan_called == 5
    assert hook._post_scan_called == 5
    assert hook2._pre_scan_called == 2
    assert hook2._post_scan_called == 2
    assert hook3._pre_scan_called == 1
    assert hook3._post_scan_called == 1
    # check that motors have moved, and are back to the original pos. (dscan)
    assert len(s.get_data()["s1vg"]) == 4
    assert roby.position == roby_pos
    assert s1vg.position == s1vg_pos
