"""Testing plot state model."""

import numpy
from silx.gui import qt
from bliss.flint.model import plot_state_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_model
from bliss.flint.model import scan_model


class CurveMock(qt.QObject, plot_item_model.CurveMixIn):

    valueChanged = qt.Signal()

    def __init__(self, xx: numpy.ndarray, yy: numpy.ndarray):
        super(CurveMock, self).__init__()
        self._xx = xx
        self._yy = yy

    def xArray(self, scan) -> numpy.ndarray:
        return self._xx

    def yArray(self, scan) -> numpy.ndarray:
        return self._yy


def test_max_compute():
    scan = None
    yy = [0, -10, 2, 5, 9, 500, 100]
    xx = numpy.arange(len(yy)) * 10

    item = plot_state_model.MaxCurveItem()
    curveItem = CurveMock(xx=xx, yy=yy)
    item.setSource(curveItem)

    result = item.compute(scan)
    assert result.nb_points == len(xx)
    assert result.max_index == 5
    assert result.max_location_x == 50
    assert result.max_location_y == 500
    assert result.min_y_value == -10


def test_max_incremental_compute_1():
    """The result is part of the increment"""
    scan = None
    yy = [0, -10, 2, 5, 9, 500, 100]
    xx = numpy.arange(len(yy)) * 10

    item = plot_state_model.MaxCurveItem()
    curveItem = CurveMock(xx=xx[: len(xx) // 2], yy=yy[: len(xx) // 2])
    item.setSource(curveItem)
    result = item.compute(scan)

    curveItem = CurveMock(xx=xx, yy=yy)
    item.setSource(curveItem)

    result = item.incrementalCompute(result, scan)
    assert result.nb_points == len(xx)
    assert result.max_index == 5
    assert result.max_location_x == 50
    assert result.max_location_y == 500
    assert result.min_y_value == -10


def test_max_incremental_compute_2():
    """The result is NOT part of the increment"""
    scan = None
    yy = [0, 10, 500, 5, 9, -10, 100]
    xx = numpy.arange(len(yy)) * 10

    item = plot_state_model.MaxCurveItem()
    curveItem = CurveMock(xx=xx[: len(xx) // 2], yy=yy[: len(xx) // 2])
    item.setSource(curveItem)
    result = item.compute(scan)

    curveItem = CurveMock(xx=xx, yy=yy)
    item.setSource(curveItem)

    result = item.incrementalCompute(result, scan)
    assert result.nb_points == len(xx)
    assert result.max_index == 2
    assert result.max_location_x == 20
    assert result.max_location_y == 500
    assert result.min_y_value == -10


def test_derivative_compute():
    """Compute the derivative function"""
    scan = scan_model.Scan()
    yy = [0] * 5 + list(range(10)) + list(reversed(range(10))) + [0] * 5
    yy = numpy.cumsum(yy)
    xx = numpy.arange(len(yy)) * 10

    item = plot_state_model.DerivativeItem()
    curveItem = CurveMock(xx=xx, yy=yy)
    item.setSource(curveItem)
    result = item.compute(scan)
    assert result is not None
    assert (
        len(item.xArray(scan))
        == len(xx) - plot_state_model.DerivativeItem.EXTRA_POINTS * 2
    )


def test_derivative_incremental_compute():
    """Compute the derivative function"""
    yy = [0] * 7 + list(range(10)) + list(reversed(range(10))) + [0] * 7
    yy = numpy.cumsum(yy)
    xx = numpy.arange(len(yy)) * 10

    scan = scan_model.Scan()
    item = plot_state_model.DerivativeItem()
    curveItem = CurveMock(xx=xx, yy=yy)
    item.setSource(curveItem)
    expected = item.compute(scan)

    result = None
    for i in [0, 5, 10, 15, 20, 25, len(xx)]:
        scan = scan_model.Scan()
        item = plot_state_model.DerivativeItem()
        curveItem = CurveMock(xx=xx[0:i], yy=yy[0:i])
        item.setSource(curveItem)
        if result is None:
            try:
                result = item.compute(scan)
            except plot_model.ComputeError as e:
                result = e.result
        else:
            result = item.incrementalCompute(result, scan)

    assert result is not None
    numpy.testing.assert_array_almost_equal(expected.xx, result.xx, decimal=5)
    numpy.testing.assert_array_almost_equal(expected.yy, result.yy)
    numpy.testing.assert_array_almost_equal(expected.nb_points, result.nb_points)
