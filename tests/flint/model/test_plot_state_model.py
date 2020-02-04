"""Testing plot state model."""

import numpy
from silx.gui import qt
from bliss.flint.model import plot_state_model
from bliss.flint.model import plot_item_model


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
