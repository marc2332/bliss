# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
import numpy


def peak(x, y):
    return x[y.argmax()]


def com(x, y):
    return numpy.sum(x * y) / numpy.sum(y)


def cen(x, y):
    half_val = (max(y) + min(y)) / 2.
    nb_value = len(x)
    index_above_half = numpy.where(y >= half_val)[0]
    slope = numpy.gradient(y, x)

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
