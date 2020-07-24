# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss.common import scans
from bliss.scanning.acquisition.motor import MeshStepTriggerMaster


def test_motor_pos__mesh2d():
    motor_pos = MeshStepTriggerMaster._interleaved_motor_pos([1, 2], [10, 20])
    expected = numpy.array([1, 2, 1, 2])
    numpy.testing.assert_array_almost_equal(motor_pos[0], expected)
    expected = numpy.array([10, 10, 20, 20])
    numpy.testing.assert_array_almost_equal(motor_pos[1], expected)


def test_motor_pos__mesh2d_backnforth():
    motor_pos = MeshStepTriggerMaster._interleaved_motor_pos(
        [1, 2], [10, 20], backnforth1=True
    )
    expected = numpy.array([2, 1, 1, 2])
    numpy.testing.assert_array_almost_equal(motor_pos[0], expected)
    expected = numpy.array([10, 10, 20, 20])
    numpy.testing.assert_array_almost_equal(motor_pos[1], expected)


def test_motor_pos__mesh3d():
    motor_pos = MeshStepTriggerMaster._interleaved_motor_pos(
        [1, 2], [10, 20], [100, 200]
    )
    expected = numpy.array([1, 2, 1, 2, 1, 2, 1, 2])
    numpy.testing.assert_array_almost_equal(motor_pos[0], expected)
    expected = numpy.array([10, 10, 20, 20, 10, 10, 20, 20])
    numpy.testing.assert_array_almost_equal(motor_pos[1], expected)
    expected = numpy.array([100, 100, 100, 100, 200, 200, 200, 200])
    numpy.testing.assert_array_almost_equal(motor_pos[2], expected)


def test_motor_pos__mesh3d_backnforth():
    motor_pos = MeshStepTriggerMaster._interleaved_motor_pos(
        [1, 2], [10, 20], [100, 200], backnforth1=True
    )
    expected = numpy.array([2, 1, 1, 2, 2, 1, 1, 2])
    numpy.testing.assert_array_almost_equal(motor_pos[0], expected)
    expected = numpy.array([10, 10, 20, 20, 10, 10, 20, 20])
    numpy.testing.assert_array_almost_equal(motor_pos[1], expected)
    expected = numpy.array([100, 100, 100, 100, 200, 200, 200, 200])
    numpy.testing.assert_array_almost_equal(motor_pos[2], expected)


def test_amesh(session):
    robz2 = session.env_dict["robz2"]
    robz = session.env_dict["robz"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    s = scans.amesh(
        robz2,
        0,
        10,
        4,
        robz,
        0,
        5,
        2,
        0.01,
        simul_counter,
        return_scan=True,
        save=False,
    )
    assert robz2.position == 10
    assert robz.position == 5
    scan_data = s.get_data()
    assert len(scan_data["robz2"]) == 15
    assert len(scan_data["robz"]) == 15
    assert scan_data["robz2"][0] == 0
    assert scan_data["robz2"][4] == 10
    assert scan_data["robz2"][-1] == 10
    assert scan_data["robz"][0] == 0
    assert scan_data["robz"][-1] == 5
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_dmesh(session):
    robz2 = session.env_dict["robz2"]
    robz = session.env_dict["robz"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    start_robz2 = robz2.position
    start_robz = robz.position
    s = scans.dmesh(
        robz2,
        -5,
        5,
        4,
        robz,
        -3,
        3,
        2,
        0.01,
        simul_counter,
        return_scan=True,
        save=False,
    )
    assert robz2.position == start_robz2
    assert robz.position == start_robz
    scan_data = s.get_data()
    assert len(scan_data["robz2"]) == 15
    assert len(scan_data["robz"]) == 15
    assert scan_data["robz2"][0] == start_robz2 - 5
    assert scan_data["robz2"][-1] == start_robz2 + 5
    assert scan_data["robz"][0] == start_robz - 3
    assert scan_data["robz"][-1] == start_robz + 3
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_d3mesh(session):
    robz2 = session.env_dict["robz2"]
    robz = session.env_dict["robz"]
    roby = session.env_dict["roby"]
    simul_counter = session.env_dict["sim_ct_gauss"]
    start_robz2 = robz2.position
    start_robz = robz.position
    start_roby = robz.position
    s = scans.d3mesh(
        robz2,
        -5,
        5,
        3,
        robz,
        -3,
        3,
        2,
        roby,
        -3,
        3,
        1,
        0.01,
        simul_counter,
        return_scan=True,
        save=False,
    )
    assert robz2.position == start_robz2
    assert robz.position == start_robz
    assert roby.position == start_roby
    scan_data = s.get_data()
    size = (3 + 1) * (2 + 1) * (1 + 1)
    assert len(scan_data["robz2"]) == size
    assert len(scan_data["robz"]) == size
    assert len(scan_data["roby"]) == size
    assert scan_data["robz2"][0] == start_robz2 - 5
    assert scan_data["robz2"][-1] == start_robz2 + 5
    assert scan_data["robz"][0] == start_robz - 3
    assert scan_data["robz"][-1] == start_robz + 3
    assert scan_data["roby"][0] == start_roby - 3
    assert scan_data["roby"][-1] == start_roby + 3
    assert numpy.array_equal(scan_data["sim_ct_gauss"], simul_counter.data)


def test_dmesh_return_to_target_pos(default_session, beacon):
    m0 = beacon.get("m0")
    robz = beacon.get("robz")
    diode = beacon.get("diode")
    m0.move(1.5)
    s = scans.dmesh(robz, -0.1, 0.1, 2, m0, -1.1, 1.1, 2, 0, diode, save=False)
    assert pytest.approx(m0._set_position) == 1.5
    d = s.get_data()
    assert min(d[m0]) == pytest.approx(0.0)
    assert max(d[m0]) == pytest.approx(3.0)
