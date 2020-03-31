# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import numpy
import typing


def peak(x: numpy.ndarray, y: numpy.ndarray) -> float:
    """Returns the x location of the peak.

    On the current implementation the peak is defined as the max of the y.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations
    """
    return x[numpy.nanargmax(y)]


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
    index = numpy.nanargmax(y)
    return x[index], y[index]


def com(x: numpy.ndarray, y: numpy.ndarray) -> float:
    """Returns the location of the center of the mass.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations
    """
    return numpy.sum(x * y) / numpy.sum(y)


def cen(x: numpy.ndarray, y: numpy.ndarray) -> typing.Tuple[float, float]:
    """Returns the location of center including the full width at half maximum.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x: A numpy array of the X locations
        y: A numpy array of the Y locations

    Returns:
        A tuple containing the location of the center, and the fwhm
    """
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

    return cfwhm, fwhm
