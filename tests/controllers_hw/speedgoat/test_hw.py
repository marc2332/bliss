# -*- coding: utf-8 -*-
#
# This file is part of the mechatronic project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
import pytest

from bliss.controller.speedgoat import xpc

pytestmark = pytest.mark.speedgoat


def test_read_scalar_types(speedgoat):
    get = xpc.get_param_value_from_name
    assert get(speedgoat, "bool_false_scalar", "Value") == False
    assert get(speedgoat, "bool_true_scalar", "Value") == True
    assert get(speedgoat, "uint8_scalar", "Value") == 23
    assert get(speedgoat, "int8_scalar", "Value") == -11
    assert get(speedgoat, "uint16_scalar", "Value") == 2300
    assert get(speedgoat, "int16_scalar", "Value") == -1100
    assert get(speedgoat, "uint32_scalar", "Value") == 230000
    assert get(speedgoat, "int32_scalar", "Value") == -110000
    assert get(speedgoat, "single_scalar", "Value") == pytest.approx(-2.3e-5)
    assert get(speedgoat, "double_scalar", "Value") == pytest.approx(5.43e23)


def test_read_1d_types(speedgoat):
    get = xpc.get_param_value_from_name

    bool_1d = get(speedgoat, "bool_1d", "Value")
    assert bool_1d.dtype == "bool"
    assert bool_1d.size == 4
    assert bool_1d.shape == (4,)
    assert numpy.array_equal(bool_1d, [True, False, False, True])

    uint8_1d = get(speedgoat, "uint8_1d", "Value")
    assert uint8_1d.dtype == "uint8"
    assert uint8_1d.size == 7
    assert uint8_1d.shape == (7,)
    assert numpy.array_equal(uint8_1d, [1, 2, 3, 4, 253, 254, 255])

    int8_1d = get(speedgoat, "int8_1d", "Value")
    assert int8_1d.dtype == "int8"
    assert int8_1d.size == 7
    assert int8_1d.shape == (7,)
    assert numpy.array_equal(int8_1d, [1, -2, 3, -4, 125, -126, 127])

    uint16_1d = get(speedgoat, "uint16_1d", "Value")
    assert uint16_1d.dtype == "uint16"
    assert uint16_1d.size == 7
    assert uint16_1d.shape == (7,)
    assert numpy.array_equal(uint16_1d, [10, 20, 30, 40, 2530, 2540, 2550])

    int16_1d = get(speedgoat, "int16_1d", "Value")
    assert int16_1d.dtype == "int16"
    assert int16_1d.size == 7
    assert int16_1d.shape == (7,)
    assert numpy.array_equal(int16_1d, [10, -20, 30, -40, 1250, -1260, 1270])

    uint32_1d = get(speedgoat, "uint32_1d", "Value")
    assert uint32_1d.dtype == "uint32"
    assert uint32_1d.size == 7
    assert uint32_1d.shape == (7,)
    assert numpy.array_equal(uint32_1d, [100, 200, 300, 400, 25300, 25400, 25500])

    int32_1d = get(speedgoat, "int32_1d", "Value")
    assert int32_1d.dtype == "int32"
    assert int32_1d.size == 7
    assert int32_1d.shape == (7,)
    assert numpy.array_equal(int32_1d, [100, -200, 300, -400, 12500, -12600, 12700])

    single_1d = get(speedgoat, "single_1d", "Value")
    assert single_1d.dtype == "single"
    assert single_1d.size == 4
    assert single_1d.shape == (4,)
    assert pytest.approx(single_1d) == [1.1, -2.23, 4.4, 55.32]

    double_1d = get(speedgoat, "double_1d", "Value")
    assert double_1d.dtype == "double"
    assert double_1d.size == 4
    assert double_1d.shape == (4,)
    assert pytest.approx(double_1d) == [1.1, -2.23, 4.4, 55.32]


def test_read_2d_types(speedgoat):
    get = xpc.get_param_value_from_name

    bool_2d = get(speedgoat, "bool_2d", "Value")
    assert bool_2d.dtype == "bool"
    assert bool_2d.size == 8
    assert bool_2d.shape == (2, 4)
    assert numpy.array_equal(bool_2d, 2 * [[True, False, False, True]])

    uint8_2d = get(speedgoat, "uint8_2d", "Value")
    assert uint8_2d.dtype == "uint8"
    assert uint8_2d.size == 28
    assert uint8_2d.shape == (4, 7)
    assert numpy.array_equal(uint8_2d, 4 * [[1, 2, 3, 4, 253, 254, 255]])

    int8_2d = get(speedgoat, "int8_2d", "Value")
    assert int8_2d.dtype == "int8"
    assert int8_2d.size == 28
    assert int8_2d.shape == (4, 7)
    assert numpy.array_equal(int8_2d, 4 * [[1, -2, 3, -4, 125, -126, 127]])

    uint16_2d = get(speedgoat, "uint16_2d", "Value")
    assert uint16_2d.dtype == "uint16"
    assert uint16_2d.size == 28
    assert uint16_2d.shape == (4, 7)
    assert numpy.array_equal(uint16_2d, 4 * [[10, 20, 30, 40, 2530, 2540, 2550]])

    int16_2d = get(speedgoat, "int16_2d", "Value")
    assert int16_2d.dtype == "int16"
    assert int16_2d.size == 28
    assert int16_2d.shape == (4, 7)
    assert numpy.array_equal(int16_2d, 4 * [[10, -20, 30, -40, 1250, -1260, 1270]])

    uint32_2d = get(speedgoat, "uint32_2d", "Value")
    assert uint32_2d.dtype == "uint32"
    assert uint32_2d.size == 28
    assert uint32_2d.shape == (4, 7)
    assert numpy.array_equal(uint32_2d, 4 * [[100, 200, 300, 400, 25300, 25400, 25500]])

    int32_2d = get(speedgoat, "int32_2d", "Value")
    assert int32_2d.dtype == "int32"
    assert int32_2d.size == 28
    assert int32_2d.shape == (4, 7)
    assert numpy.array_equal(
        int32_2d, 4 * [[100, -200, 300, -400, 12500, -12600, 12700]]
    )

    single_2d = get(speedgoat, "single_2d", "Value")
    assert single_2d.dtype == "single"
    assert single_2d.size == 12
    assert single_2d.shape == (3, 4)
    assert pytest.approx(single_2d) == 3 * [[1.1, -2.23, 4.4, 55.32]]

    double_2d = get(speedgoat, "double_2d", "Value")
    assert double_2d.dtype == "double"
    assert double_2d.size == 12
    assert double_2d.shape == (3, 4)
    assert pytest.approx(double_2d) == 3 * [[1.1, -2.23, 4.4, 55.32]]
