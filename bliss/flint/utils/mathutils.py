# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Tuple
from typing import NamedTuple

import numpy
import scipy.optimize

from . import _math_pymca


def derivate(
    xx: numpy.ndarray, yy: numpy.ndarray
) -> Tuple[numpy.ndarray, numpy.ndarray]:
    """
    Compute derivative function from the curve `xx`, `yy`
    """
    return _math_pymca.derivate(xx, yy)


def center_of_mass(xx, yy):
    values = numpy.array(yy, dtype=numpy.float64)
    axis = numpy.array(xx, dtype=numpy.float64)
    sum_ = numpy.sum(values)
    return numpy.sum(axis * values) / sum_


def _gaussian(x, p):
    """
    Helper function to fit a gaussian with scipy.

    The gaussian have a parametric center, sigma, height and fixed background.

    Args:
        p[0] center
        p[1] sigma
        p[2] height
        p[3] background
    """
    # FIXME: Use numexpr to speed up the computation
    return p[3] + p[2] * numpy.exp(-(x - p[0]) ** 2 / (2 * p[1] ** 2))


class GaussianFitResult(NamedTuple):
    """Description of the gaussian modelization"""

    fwhm: float
    std: float
    pos_x: float
    height: float
    background: float

    def transform(self, xx: numpy.ndarray) -> numpy.ndarray:
        """Transform a X array using the fitted function"""
        p = [self.pos_x, self.std, self.height, self.background]
        return _gaussian(xx, p)


def fit_gaussian(xx: numpy.ndarray, yy: numpy.ndarray) -> GaussianFitResult:
    """
    Fit `xx` and `yy` curve with a gaussian and returns its characteristics.
    """
    # Initial guess
    background = numpy.min(yy)
    height = numpy.max(yy) - background
    ipos = numpy.argmax(yy)
    pos = xx[ipos]
    # FIXME: It would be good to provide a better guess for sigma
    p0 = [pos, 1, height, background]

    # Distance to the target function
    errfunc = lambda p, x, y: _gaussian(x, p) - y
    p1, success = scipy.optimize.leastsq(errfunc, p0[:], args=(xx, yy))
    if not success:
        raise ValueError("Input data can't be fitted")

    # Compute characteristics
    fit_mean, fit_std, fit_height, fit_background = p1
    fwhm = 2 * numpy.sqrt(2 * numpy.log(2)) * fit_std
    return GaussianFitResult(fwhm, fit_std, fit_mean, fit_height, fit_background)
