# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from math import sqrt
import gevent
from bliss.common.standard import move
from bliss.config.conductor.client import get_default_connection
from bliss.physics.trajectory import LinearTrajectory


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
        instants=(sqrt(1 / 20.), 3.625, 8.125, 9 + sqrt(1 / 80.), 9.25),
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
        instants=(sqrt(1 / 20.), 3.625, 8.125, 9 + sqrt(1 / 80.), 9.25),
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
        instants=(sqrt(2 / 5.), 1, 1 + sqrt(4 / 5.)),
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


def test_steps_per_unit_modified(beacon, factor=2., offset=10.):
    # LOAD CONFIG
    robz_cfg = beacon.get_config("robz")

    # GET SPU FROM CONFIG
    spu_0 = robz_cfg["steps_per_unit"]

    # CREATE ROBZ
    robz = beacon.get("robz")

    # SET THE OFFSET
    robz.position = robz.dial + offset
    assert robz.offset == offset

    # MOVE ROBZ TO A POSITION != 0
    robz.move(1.0 + offset)

    # READ PARAMETERS WHICH DEPENDS ON SPU
    values_0 = (robz.dial, robz.position, robz._set_position)

    # DELETE ROBZ AND RELOAD CONFIG
    del robz
    beacon.reload()
    robz_cfg = beacon.get_config("robz")

    # MODIFY THE SPU IN CONFIG
    spu_1 = robz_cfg["steps_per_unit"] = robz_cfg["steps_per_unit"] * factor

    # CREATE ROBZ
    robz = beacon.get("robz")

    # CHECK THAT THE POSITIONS ARE UPDATED
    values_1 = (robz.dial, robz.position, robz._set_position)

    assert spu_1 == spu_0 * factor
    assert values_1[0] * factor == values_0[0]
    assert (values_1[1] - offset) * factor == (values_0[1] - offset)
    assert (values_1[2] - offset) * factor == (values_0[2] - offset)


def test_1st_time_cfg_wrong_acc_vel(beacon, beacon_directory):
    client_conn = get_default_connection()
    redis_conn = client_conn.get_redis_connection()

    m = beacon.get("invalid_acc")

    with pytest.raises(RuntimeError):
        # this will initialize the axis object,
        # and exception will be triggered for
        # acceleration
        m.position

    # change config with good acc
    m.config.set("acceleration", 100)
    m.config.save()

    m.apply_config(reload=True)

    assert m.acceleration == 100

    m = beacon.get("invalid_vel")
    with pytest.raises(RuntimeError):
        m.position
    m.config.set("velocity", 10)
    m.config.save()
    m.apply_config(reload=True)
    assert m.velocity == 10


def test_move_std_func_no_wait_motor_stop(beacon, roby, robz):
    move(roby, 1e6, robz, 1e6, wait=False)  # move == mv

    assert "MOVING" in roby.state
    assert "MOVING" in robz.state

    with gevent.Timeout(1):
        roby.stop()

    assert "READY" in roby.state
    assert "READY" in robz.state
