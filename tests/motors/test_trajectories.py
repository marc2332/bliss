# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
from bliss.common import event
import numpy
from unittest import mock


def test_traj_from_calc(s1hg, s1b, s1f, s1u, s1d):
    tg = s1hg.scan_on_trajectory(0, 5, 100, 0.01)
    trajectories = tg.trajectories

    assert set([a.name for a in tg.axes]) == set(["s1u", "s1d", "s1f", "s1b"])

    for traj in trajectories:
        if traj.axis.name in ("s1u", "s1d"):
            assert not numpy.any(traj.pvt["position"])
        elif traj.axis.name in ("s1f", "s1b"):
            assert pytest.approx(traj.pvt[:-1]["position"], 2.5)
        assert len(traj.pvt) == 100 + 2  # include start, final extra points for traj.

    assert len(tg.disabled_axes) == 0

    assert tg.calc_axis == s1hg

    s1hg.dial = -1
    assert pytest.approx(s1f.offset, -0.5)
    assert pytest.approx(s1b.offset, -0.5)

    tg.prepare()
    assert tg._TrajectoryGroup__trajectories_dialunit
    for i, traj in enumerate(tg._TrajectoryGroup__trajectories_dialunit):
        if traj.axis.name in ("s1u", "s1d"):
            assert not numpy.any(traj.pvt["position"])
        elif traj.axis.name in ("s1f", "s1b"):
            user_pos_traj = trajectories[i].pvt["position"] * traj.axis.steps_per_unit
            assert numpy.allclose(
                user_pos_traj - traj.pvt["position"],
                [-0.5 * traj.axis.steps_per_unit] * 102,
            )

    tg.move_to_start()

    tg.disable_axis(s1u)
    tg.disable_axis(s1d)
    assert len(tg.disabled_axes) == 2
    assert set(tg.disabled_axes) == set([s1u, s1d])

    def check_trajectories(*trajectories):
        assert len(trajectories) == 2

    with mock.patch.object(s1f.controller, "prepare_trajectory", check_trajectories):
        tg.prepare()

    tg.enable_axis(s1d)
    assert len(tg.disabled_axes) == 1
    assert set(tg.disabled_axes) == set([s1u])

    def check_trajectories(*trajectories):
        assert len(trajectories) == 3

    with mock.patch.object(s1f.controller, "prepare_trajectory", check_trajectories):
        tg.prepare()

    tg.move_to_end()


def test_traj_from_calc_from_calc(calc_mot2, calc_mot1, roby):
    tg = calc_mot2.scan_on_trajectory(0, 1, 100, 0.1)
    trajectories = tg.trajectories

    assert set([t.axis.name for t in trajectories]) == set(["roby"])
