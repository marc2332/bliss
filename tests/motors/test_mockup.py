

from math import sqrt
from collections import OrderedDict

import pytest

from bliss.physics.trajectory import LinearTrajectory


parameters = [
    dict(
        desc="long movement (reaches top velocity)",
        motion=OrderedDict(pi=10, pf=100, velocity=10, acceleration=40, ti=0),
        expected_trajectory=OrderedDict(
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
        instants=(sqrt(1 / 20.), 3.625, 8.125, 9 + sqrt(1 / 80.), 9.25),
    ),
    dict(
        desc="negative long movement (reaches top velocity)",
        motion=OrderedDict(pi=-10, pf=-100, velocity=10, acceleration=40, ti=0),
        expected_trajectory=OrderedDict(
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
        instants=(sqrt(1 / 20.), 3.625, 8.125, 9 + sqrt(1 / 80.), 9.25),
    ),
    dict(
        desc="short movement",
        motion=OrderedDict(pi=10, pf=15, velocity=10, acceleration=5, ti=0),
        expected_trajectory=OrderedDict(
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
        instants=(sqrt(2 / 5.), 1, 1 + sqrt(4 / 5.)),
    ),
    dict(
        desc="negative short movement",
        motion=OrderedDict(pi=2.5, pf=-2.5, velocity=10, acceleration=5, ti=0),
        expected_trajectory=OrderedDict(
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
        instants=(sqrt(2 / 5.), 1, 1 + sqrt(4 / 5.)),
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
