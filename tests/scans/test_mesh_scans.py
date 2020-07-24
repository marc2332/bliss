# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
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
