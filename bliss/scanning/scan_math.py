# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import numpy
import typing
import logging
from collections import namedtuple


_logger = logging.getLogger(__name__)

Cen = namedtuple("center", ["position", "fwhm"])


Peak = namedtuple("peak", ["position", "value"])


def peak(x: numpy.ndarray, y: numpy.ndarray) -> float:
    """Returns the x location of the peak.

    On the current implementation the peak is defined as the max of the y.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations
    """
    # Use peak2 to reuse the argument checks
    return peak2(x, y)[0]


def peak2(x: numpy.ndarray, y: numpy.ndarray) -> typing.Tuple[float, float]:
    """Returns the location of the peak.

    On the current implementation the peak is defined as the max of the y.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations

    Returns:
        A tuple containing the x location and the y location of the peak
    """
    if x.shape != y.shape:
        raise TypeError("x and y arrays do not have the same size.")

    if x.ndim != 1:
        raise TypeError("x and y arrays must have a single dimension.")

    if x.size == 0:
        _logger.warning("Input data is empty")
        return Peak(numpy.nan, numpy.nan)

    try:
        index = numpy.nanargmax(y)
    except ValueError:
        # No finite values found
        return Peak(numpy.nan, numpy.nan)
    return Peak(x[index], y[index])


def com(x: numpy.ndarray, y: numpy.ndarray, shift_y=True) -> float:
    """Returns the location of the center of the mass.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations
        shift_y: shift y values so that they are positiv to
                          make sure the com also works for signals
                          with `negative` mass 
    """
    if x.shape != y.shape:
        raise TypeError("x and y arrays do not have the same size.")

    if x.ndim != 1:
        raise TypeError("x and y arrays must have a single dimension.")

    if x.size == 0:
        _logger.warning("Input data is empty")
        return numpy.nan

    if shift_y:
        miny = numpy.min(y)
        y = y - miny
        den = numpy.sum(y, dtype=numpy.float)
        if den > 0:
            return numpy.sum(x * y, dtype=numpy.float) / den
        else:
            # let it raise exception if x.size is 0?
            return numpy.sum(x, dtype=numpy.float) / x.size


def cen(x: numpy.ndarray, y: numpy.ndarray) -> typing.Tuple[float, float]:
    """Returns the location of center including the full width at half maximum.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations

    Returns:
        A tuple containing the location of the center, and the fwhm
    """
    if x.shape != y.shape:
        raise TypeError("x and y arrays do not have the same size.")

    if x.ndim != 1:
        raise TypeError("x and y arrays must have a single dimension.")

    if x.size < 2:
        # gradient expect 2 points
        return Cen(numpy.nan, numpy.nan)

    slope = numpy.gradient(y, x)
    # check if function is continuous
    if numpy.inf in slope or -numpy.inf in slope:
        # if not remove double values
        adjacent_index = dict()
        prev_x = None
        for i, xval in enumerate(x):
            if prev_x is None:
                prev_x = xval
                continue
            if prev_x == xval:
                l = adjacent_index.setdefault(xval, list())
                l.append(i)
            prev_x = xval
        remove_index = list()
        for index in adjacent_index.values():
            min_index = min(index) - 1
            y[min_index] = y[[min_index] + index].mean()
            remove_index.extend(index)

        x = numpy.delete(x, remove_index)
        y = numpy.delete(y, remove_index)
        slope = numpy.gradient(y, x)

    half_val = (max(y) + min(y)) / 2.
    nb_value = len(x)
    index_above_half = numpy.where(y >= half_val)[0]
    if index_above_half[0] != 0 and index_above_half[-1] != (nb_value - 1):
        # standard peak
        if len(index_above_half) == 1:  # only one point above half_value
            indexes = [index_above_half[0] - 1, index_above_half[0] + 1]
        else:
            indexes = [index_above_half[0], index_above_half[-1]]
    elif index_above_half[0] == 0 and index_above_half[-1] == (nb_value - 1):
        index_below_half = numpy.where(y <= half_val)[0]
        if len(index_below_half) == 1:
            indexes = [index_below_half[0] - 1, index_below_half[0] + 1]
        else:
            indexes = [index_below_half[0], index_below_half[-1]]
    elif index_above_half[0] == 0:  # falling edge
        indexes = [index_above_half[-1]]
    else:  # raising edge
        indexes = [index_above_half[0]]

    fwhms = numpy.array([x[i] + ((half_val - y[i]) / slope[i]) for i in indexes])
    fwhm = fwhms.max() - fwhms.min()
    cfwhm = fwhms.mean()

    return Cen(cfwhm, fwhm)
