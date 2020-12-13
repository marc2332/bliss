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
from contextlib import contextmanager
from scipy.signal import savgol_filter


logger = logging.getLogger(__name__)

Cen = namedtuple("center", ["position", "fwhm"])

Peak = namedtuple("peak", ["position", "value"])


def peak(x: numpy.ndarray, y: numpy.ndarray) -> float:
    """Returns the x location of the peak.

    On the current implementation the peak is defined as the max of the y.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        x location of the peak
    """
    return peak2(x, y)[0]


def peak2(x: numpy.ndarray, y: numpy.ndarray) -> typing.Tuple[float, float]:
    """Returns the location of the peak.

    On the current implementation the peak is defined as the max of the y.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        A tuple containing the x location and the y location of the peak
    """
    if not _check_arrays(x, y):
        return Peak(numpy.nan, numpy.nan)
    with _capture_exceptions():
        x, y = _extract_finite(x, y)
        index = numpy.argmax(y)
        return Peak(x[index], y[index])
    return Peak(numpy.nan, numpy.nan)


def com(x: numpy.ndarray, y: numpy.ndarray, visual=True) -> float:
    """Returns the location of the center of the mass.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations
        visual (bool): "visual" centroid instead of the "data" centroid

    Returns:
        Center of mass
    """
    if not _check_arrays(x, y):
        return numpy.nan
    with _capture_exceptions():
        x, y = _extract_finite(x, y)
        if visual:
            x, y = _extract_unique(x, y)
            y -= y.min()
        return numpy.sum(x * _calc_weights(y), dtype=numpy.float)
    return numpy.nan


def cen(x: numpy.ndarray, y: numpy.ndarray) -> typing.Tuple[float, float]:
    """Returns the location of center including the full width at half maximum.

    The algorithm was designed to be fast. It is not using any fit function.

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        A tuple containing the location of the center and the fwhm
    """
    if not _check_arrays(x, y):
        return Cen(numpy.nan, numpy.nan)
    with _capture_exceptions():
        x, y = _extract_finite(x, y)
        x, y = _extract_unique(x, y)  # already does sorting
        return _calc_cen(x, y)
    return Cen(numpy.nan, numpy.nan)


def _check_arrays(x, y):
    """
    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        bool: valid data

    Raises:
        TypeError: wrong shape
    """
    if x.shape != y.shape:
        raise TypeError("x and y arrays do not have the same size.")

    if x.ndim != 1:
        raise TypeError("x and y arrays must have a single dimension.")

    if x.size == 0:
        logger.warning("Input data is empty.")
        return False

    return True


def _extract_finite(x, y):
    """Keep only finite (x, y) pairs

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        tuple: (x, y)

    Raises:
        ValueError: no finite values
    """
    mask = numpy.isfinite(x) & numpy.isfinite(y)
    if not mask.any():
        raise ValueError("Input data has no finite values.")
    x = x[mask]
    y = y[mask]
    return x, y


def _extract_unique(x, y):
    """Keep (x, y) pairs with a unique x value (sorts by x value as well)

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        tuple: (x, y)
    """
    x, idx = numpy.unique(x, return_index=True)
    y = y[idx]
    return x, y


def _sort_arrays(x, y):
    """Sort (x, y) pairs by x value

    Args:
        x (ndarray): X locations
        y (ndarray): Y locations

    Returns:
        tuple: (x, y)
    """
    idx = numpy.argsort(x)
    x = x[idx]
    y = y[idx]
    return x, y


@contextmanager
def _capture_exceptions():
    """Capture and log exceptions
    """
    try:
        with numpy.errstate(all="raise"):
            yield
    except Exception as e:
        logger.warning(f"Error in calculation: {e}")


def _calc_weights(y):
    """Make positive with sum(y)==1

    Args:
        y (ndarray): Y locations

    Returns:
        num or numpy.ndarray:
    """
    if (y < 0).any():
        y -= y.min()
    ysum = numpy.sum(y, dtype=numpy.float)
    if ysum:
        return y / ysum
    else:
        return numpy.float(1 / y.size)  # no need to replicate


def _optimize_gradient(gradient, i, grad_down):
    """Extract the steepest gradient in the surrrounding of index `i`.

    Args:
        gradient (ndarray):
        i (num):
        grad_down (bool):

    Returns:
        num
    """
    n = max(min(gradient.size // 4, 5), 1)
    if grad_down:
        idx_valid = numpy.where(gradient < 0)[0]
        selfunc = min
    elif grad_down is None:
        idx_valid = numpy.where(gradient != 0)[0]
        selfunc = lambda x: max(x.min(), x.max(), key=abs)
    else:
        idx_valid = numpy.where(gradient > 0)[0]
        selfunc = max
    idx = idx_valid[numpy.argsort(numpy.abs(idx_valid - i))]
    if not idx.size:
        if grad_down is None:
            return 0.
        else:
            return _optimize_gradient(gradient, i, None)
    return selfunc(gradient[idx[:n]])


def _optimize_limits(x, y, y_lim, idx_lim, grad_down):
    """Calculate x values from the data index limits.

    Args:
        x (ndarray): X locations (unique and sorted)
        y (ndarray): Y locations
        y_lim (list): Target y values of the limit start and end
        idx_lim (list): Data start and end index of the limit
        grad_down (list): Gradient down or up at the limits

    Returns:
        2-tuple: (start, stop)
    """
    x_start, x_end = x[idx_lim]

    # Gradient in each point
    gradient = numpy.gradient(y, x)
    idx_nonzero = numpy.where(gradient != 0)[0]
    if not idx_nonzero.size:
        # Flat signal
        return x[0], x[-1]

    # Gradient at start and end of the peak's FWHM.
    gradient_start = _optimize_gradient(gradient, idx_lim[0], grad_down=grad_down[0])
    gradient_end = _optimize_gradient(gradient, idx_lim[1], grad_down=grad_down[1])

    # Extrapolate the x values at the start and end (corresponding to idx_lim)
    # so that the corresponding y values are theoretically `y_lim`
    dmax = x[-1] - x[0]
    if gradient_start:
        dx = (y_lim[0] - y[idx_lim[0]]) / gradient_start
        if abs(dx) <= dmax:
            x_start += dx
    if gradient_end:
        dx = (y_lim[1] - y[idx_lim[1]]) / gradient_end
        if abs(dx) <= dmax:
            x_end += dx

    return x_start, x_end


def _cen_from_limits(x, y, y_lim, idx_lim, grad_down):
    """Cen from the start and end index.

    Args:
        x (ndarray): X locations (unique and sorted)
        y (ndarray): Y locations
        y_lim (list): Target y values of the limit start and end
        idx_lim (list): Data start and end index of the limit
        grad_down (list): Gradient down or up at the limits

    Returns:
        Cen:
    """
    result = _optimize_limits(x, y, y_lim, idx_lim, grad_down)
    x_start, x_end = result
    center = (x_start + x_end) / 2
    fwhm = x_end - x_start
    return Cen(center, fwhm)


def _inlier_mask(x, nsigma=3, pdf="normal", noutliers=None):
    """Outlier detection based on the median-absolute-deviation from the median.

        MAD = cte * median(|x-median(x)|)

    Args:
        x (ndarray):
        nsigma (num):
        pdf (str): determines the `cte`
        noutliers (num): fixed number of outliers

    Returns:
        ndarray(bool): |x-median(x)| <= nsigma*MAD
    """
    if x.size == 0:
        return numpy.array([], dtype=bool)

    # Deviation form medium
    diff = abs(x - numpy.median(x))

    # Fixed number of outliers
    if noutliers:
        inlier_mask = numpy.full(x.size, True, dtype=bool)
        inlier_mask[(-diff).argsort()[0:noutliers]] = False
        return inlier_mask

    # median-absolute-deviation
    nMAD = numpy.median(diff) * nsigma
    if pdf == "normal":
        nMAD *= 1.4826

    # inliers
    if nMAD == 0:
        return numpy.full(x.shape, True, dtype=bool)
    else:
        return diff <= nMAD


def _fill_outliers(x, **kw):
    """Replace outliers with the average of the neighbouring inliers

    Args:
        x (ndarray):
        kw: see `_inlier_mask`

    Returns:
        ndarray
    """
    outlier_mask = ~_inlier_mask(x, **kw)
    fidx = numpy.arange(x.size)
    bidx = numpy.arange(x.size)
    fidx[outlier_mask] = -1
    bidx[outlier_mask] = x.size
    numpy.maximum.accumulate(fidx, out=fidx)
    numpy.minimum.accumulate(bidx[::-1], out=bidx[::-1])
    fidx2 = numpy.clip(fidx, 0, x.size - 1)
    bidx2 = numpy.clip(bidx, 0, x.size - 1)
    fx = numpy.where(fidx > 0, x[fidx2], numpy.nan)
    bx = numpy.where(bidx < x.size, x[bidx2], numpy.nan)
    return numpy.nanmean([fx, bx], axis=0)


def _smooth(y):
    """Smooth signal

    Args:
        y (ndarray):

    Returns:
        ndarray
    """
    window_length = y.size // 4
    window_length += not (window_length % 2)
    poly_order = min(window_length - 1, 3)
    if poly_order:
        return savgol_filter(y, window_length, poly_order)
    else:
        return y


def _extract_noise(y):
    """Extract the noise of a signal

    Args:
        y (ndarray):

    Returns:
        ndarray
    """
    return y - _smooth(y)


def _calc_cen(x, y):
    """Center and FWHM

    Args:
        x (ndarray): X locations (unique and sorted)
        y (ndarray): Y locations

    Returns:
        Cen:
    """
    if len(x) == 1:
        return Cen(x[0], 0)

    # Indices of y values above the half value
    y_min = y.min()
    y_max = y.max()
    y_half = (y_min + y_max) / 2
    y_lim = [y_half, y_half]
    idx_max = x.size - 1
    idx_above_half = numpy.where(y >= y_half)[0]
    if len(idx_above_half):
        max_left = idx_above_half[0] == 0
        max_right = idx_above_half[-1] == idx_max
    else:
        idx_above_half = [0, idx_max]
        max_left = max_right = True

    # Is this a standard peak?
    if not max_left and not max_right:
        idx_lim = idx_above_half[[0, -1]]
        grad_down = [False, True]
        if idx_above_half.size == 1:  # only one point above half_value
            idx_lim[0] -= 1
            idx_lim[1] += 1
        return _cen_from_limits(x, y, y_lim, idx_lim, grad_down)

    # Is this a reversed peak?
    if max_left and max_right:
        index_below_half = numpy.where(y <= y_half)[0]
        idx_lim = index_below_half[[0, -1]]
        grad_down = [True, False]
        if index_below_half.size == 1:  # only one point below half_value
            idx_lim[0] -= 1
            idx_lim[1] += 1
        return _cen_from_limits(x, y, y_lim, idx_lim, grad_down)

    # This is either an edge or a partial peak
    idx_lim = [idx_above_half[0], idx_above_half[-1]]
    if max_left:
        # Step down
        grad_down = [True, True]
    else:
        # Step up
        grad_down = [False, False]

    x_start, x_end = _optimize_limits(x, y, y_lim, idx_lim, grad_down)
    if max_left:
        idx_edge = idx_lim[0]
        x_half = x_end
    else:
        idx_edge = idx_lim[1]
        x_half = x_start

    # Is this an edge?
    if idx_above_half.size >= 9:
        stddev_above = numpy.std(_extract_noise(y[idx_above_half]))
    else:
        stddev_above = 0
    frac_half = 1 - min(6 * stddev_above / (y_max - y_half), 1)
    frac_half = min(frac_half, 0.9)

    if max(y[idx_edge] - y_half, 0) >= frac_half * (y_max - y_half):
        # Better estimation of edge min and max:
        index_below_half = numpy.where(y < y_half)[0]
        if index_below_half.size >= 9:
            stddev_below = numpy.std(_extract_noise(y[index_below_half]))
        else:
            stddev_below = 0
        y_max -= 3 * stddev_above
        y_min += 3 * stddev_below
        if y_min >= y_max:
            # Too much noise to estimate the FWHM
            return Cen(x_half, numpy.nan)

        # FWHM of Gaussian edge:
        #  PDF(x) = exp[-(x-u)^2/(2.s^2)]/(sqrt(2.pi).s)
        #  CDF(x) = (1 + erf[(x-u)/(s.sqrt(2))])/2
        #  FWHM = 2*sqrt(2.ln(2)).s
        #  CDF(u + FWHM/2) = (1 + erf[sqrt(ln(2))])/2 ~= 0.88

        y_lim = y_min + (y_max - y_min) * numpy.array([0.12, 0.88])
        edge_mask = (y >= y_lim[0]) & (y <= y_lim[1])
        edge_idx = numpy.where(edge_mask)[0]
        edge_mask[edge_idx] = _inlier_mask(x[edge_mask])

        idx_lim = numpy.where(edge_mask)[0]
        if idx_lim.size < 2:
            # Edge is too sharp to estimate an FWHM
            return Cen(x_half, 0)

        idx_lim = idx_lim[[0, -1]]
        if max_left:
            y_lim = y_lim[::-1]
        cen = _cen_from_limits(x, y, y_lim, idx_lim, grad_down)

        # Do not allow large deviations from x_half
        if abs(cen.position - x_half) >= 0.2 * (x.max() - x.min()):
            cen = Cen(x_half, cen.fwhm)
        return cen

    # This is a partial peak: use maximum as position
    position = x[numpy.argmax(y)]
    fwhm = numpy.abs(position - x_half) * 2
    return Cen(position, fwhm)
