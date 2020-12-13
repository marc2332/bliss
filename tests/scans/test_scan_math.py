# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss.scanning import scan_math
from silx.utils import testutils


def test_cen_1_point():
    y = numpy.array([0])
    x = numpy.array([0])
    listener = testutils.TestLogging(scan_math.logger.name, error=0, warning=0, info=0)
    with listener:
        scan_math.cen(x, y)


def test_cen_4_points():
    y = numpy.array([100, 400, 400, 100])
    x = numpy.array([11, 12, 13, 14])
    result = scan_math.cen(x, y)
    # Named argument are available
    assert result.position == pytest.approx(12.5)
    assert result.fwhm == pytest.approx(3)
    # Indexed arguments are available
    assert result[0] == result.position
    assert result[1] == result.fwhm


def test_cen_incompatible_arrays():
    y = numpy.array([1, 3, 1])
    x = numpy.array([1, 2])
    with pytest.raises(TypeError):
        scan_math.cen(x, y)


def test_cen_empty():
    y = numpy.array([], dtype=float)
    x = numpy.array([], dtype=float)
    result = scan_math.cen(x, y)
    assert numpy.isnan(result.position)
    assert numpy.isnan(result.fwhm)


def test_com_4_points():
    y = numpy.array([100, 400, 400, 100])
    x = numpy.array([11, 12, 13, 14])
    result = scan_math.com(x, y)
    assert result == pytest.approx(12.5)


def test_com_incompatible_arrays():
    y = numpy.array([1, 3, 1])
    x = numpy.array([1, 2])
    with pytest.raises(TypeError):
        scan_math.com(x, y)


def test_com_empty():
    y = numpy.array([], dtype=float)
    x = numpy.array([], dtype=float)
    result = scan_math.com(x, y)
    assert numpy.isnan(result)


def test_com_zero_mass():
    y = numpy.array([0, 0, 0, 0], dtype=float)
    x = numpy.array([1, 2, 3, 4], dtype=float)
    result = scan_math.com(x, y)
    assert result == pytest.approx(2.5)


def test_peak2_4_points():
    y = numpy.array([100, 400, 399, 100])
    x = numpy.array([11, 12, 13, 14])
    result = scan_math.peak2(x, y)
    # Named argument are available
    assert result.position == pytest.approx(12)
    assert result.value == pytest.approx(400)
    # Indexed arguments are available
    assert result[0] == result.position
    assert result[1] == result.value


def test_peak2_incompatible_arrays():
    y = numpy.array([1, 3, 1])
    x = numpy.array([1, 2])
    with pytest.raises(TypeError):
        scan_math.peak2(x, y)


def test_peak2_empty():
    y = numpy.array([], dtype=float)
    x = numpy.array([], dtype=float)
    result = scan_math.peak2(x, y)
    assert numpy.isnan(result.position)
    assert numpy.isnan(result.value)


def test_peak2_all_nan():
    y = numpy.array([numpy.nan, numpy.nan, numpy.nan], dtype=float)
    x = numpy.array([1, 2, 3], dtype=float)
    result = scan_math.peak2(x, y)
    assert numpy.isnan(result.position)
    assert numpy.isnan(result.value)
