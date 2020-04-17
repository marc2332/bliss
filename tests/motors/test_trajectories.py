# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
import numpy
import math
from unittest import mock

from bliss.physics.trajectory import LinearTrajectory
from bliss.common import event


def test_traj_from_calc(s1hg, s1b, s1f, s1u, s1d):
    tg = s1hg.scan_on_trajectory(0, 5, 100, 0.01)
    trajectories = tg.trajectories

    assert set([a.name for a in tg.axes]) == set(["s1u", "s1d", "s1f", "s1b"])

    for traj in trajectories:
        if traj.axis.name in ("s1u", "s1d"):
            assert not numpy.any(traj.pvt["position"])
        elif traj.axis.name in ("s1f", "s1b"):
            assert pytest.approx(traj.pvt["position"][-2]) == 2.5
        assert len(traj.pvt) == 100 + 2  # include start, final extra points for traj.

    assert len(tg.disabled_axes) == 0

    assert tg.calc_axis == s1hg

    s1hg.dial = -1
    assert pytest.approx(s1f.offset) == -0.5
    assert pytest.approx(s1b.offset) == -0.5

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


parameters = [
    dict(
        desc="long movement (reaches top velocity)",
        motion=dict(pi=10, pf=100, velocity=10, acceleration=40, ti=0),
        expected_trajectory=dict(
            p=90,
            dp=90,
            positive=True,
            reaches_top_vel=True,
            top_vel_dp=87.5,
            top_vel_time=8.75,
            accel_dp=1.25,
            accel_time=0.25,
            duration=9.25,
            ti=0,
            ta=0.25,
            tb=9,
            tf=9.25,
            pi=10,
            pa=11.25,
            pb=98.75,
            pf=100,
        ),
        positions=(11, 45, 90, 99, 100),
        instants=(math.sqrt(1 / 20.), 3.625, 8.125, 9 + math.sqrt(1 / 80.), 9.25),
    ),
    dict(
        desc="negative long movement (reaches top velocity)",
        motion=dict(pi=-10, pf=-100, velocity=10, acceleration=40, ti=0),
        expected_trajectory=dict(
            p=-90,
            dp=90,
            positive=False,
            reaches_top_vel=True,
            top_vel_dp=87.5,
            top_vel_time=8.75,
            accel_dp=1.25,
            accel_time=0.25,
            duration=9.25,
            ti=0,
            ta=0.25,
            tb=9,
            tf=9.25,
            pi=-10,
            pa=-11.25,
            pb=-98.75,
            pf=-100,
        ),
        positions=(-11, -45, -90, -99, -100),
        instants=(math.sqrt(1 / 20.), 3.625, 8.125, 9 + math.sqrt(1 / 80.), 9.25),
    ),
    dict(
        desc="short movement",
        motion=dict(pi=10, pf=15, velocity=10, acceleration=5, ti=0),
        expected_trajectory=dict(
            p=5,
            dp=5,
            positive=True,
            reaches_top_vel=False,
            top_vel_dp=0,
            top_vel_time=0,
            accel_dp=2.5,
            accel_time=1,
            duration=2,
            ti=0,
            ta=1,
            tb=1,
            tf=2,
            pi=10,
            pa=12.5,
            pb=12.5,
            pf=15,
        ),
        positions=(11, 12.5, 14.5),
        instants=(math.sqrt(2 / 5.), 1, 1 + math.sqrt(4 / 5.)),
    ),
    dict(
        desc="negative short movement",
        motion=dict(pi=2.5, pf=-2.5, velocity=10, acceleration=5, ti=0),
        expected_trajectory=dict(
            p=-5,
            dp=5,
            positive=False,
            reaches_top_vel=False,
            top_vel_dp=0,
            top_vel_time=0,
            accel_dp=2.5,
            accel_time=1,
            duration=2,
            ti=0,
            ta=1,
            tb=1,
            tf=2,
            pi=2.5,
            pa=0,
            pb=0,
            pf=-2.5,
        ),
        positions=(1.5, 0, -2),
        instants=(math.sqrt(2 / 5.), 1, 1 + math.sqrt(4 / 5.)),
    ),
]


@pytest.mark.parametrize(
    "motion, expected_trajectory",
    [(param["motion"], param["expected_trajectory"]) for param in parameters],
    ids=[param["desc"] for param in parameters],
)
def test_trajectory(motion, expected_trajectory):
    traj = LinearTrajectory(**motion)

    for param, value in list(expected_trajectory.items()):
        assert value == pytest.approx(getattr(traj, param), param)


@pytest.mark.parametrize(
    "motion, positions, expected_instants",
    [(param["motion"], param["positions"], param["instants"]) for param in parameters],
    ids=[param["desc"] for param in parameters],
)
def test_trajectory_instant(motion, positions, expected_instants):
    traj = LinearTrajectory(**motion)

    for position, expected_instant in zip(positions, expected_instants):
        assert traj.instant(position) == pytest.approx(expected_instant)


@pytest.mark.parametrize(
    "motion, instants, expected_positions",
    [(param["motion"], param["instants"], param["positions"]) for param in parameters],
    ids=[param["desc"] for param in parameters],
)
def test_trajectory_positions(motion, instants, expected_positions):
    traj = LinearTrajectory(**motion)

    for instant, expected_position in zip(instants, expected_positions):
        assert traj.position(instant) == pytest.approx(expected_position)
