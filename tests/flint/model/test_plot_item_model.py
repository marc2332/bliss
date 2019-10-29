"""Testing plot item model."""

import numpy
from silx.gui import qt
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_model


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

    item = plot_item_model.MaxCurveItem()
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

    item = plot_item_model.MaxCurveItem()
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

    item = plot_item_model.MaxCurveItem()
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


def test_picklable():
    plot = plot_item_model.CurvePlot()
    plot.setScansStored(True)

    item = plot_item_model.CurveItem(plot)
    item.setXChannel(plot_model.ChannelRef(None, "x"))
    item.setYChannel(plot_model.ChannelRef(None, "y"))
    plot.addItem(item)

    item2 = plot_item_model.DerivativeItem(plot)
    item2.setYAxis("right")
    item2.setSource(item)
    plot.addItem(item2)

    item3 = plot_item_model.MaxCurveItem(plot)
    item3.setSource(item2)
    plot.addItem(item3)
    import pickle

    newPlot = pickle.loads(pickle.dumps(plot))
    newItems = list(newPlot.items())
    assert len(plot.items()) == len(newItems)

    # State
    assert plot.isScansStored() == newPlot.isScansStored()
    assert newItems[0].xChannel().name() == "x"
    assert newItems[0].yChannel().name() == "y"
    assert newItems[0].yAxis() == "left"
    assert newItems[1].yAxis() == "right"

    # Relationship
    assert newItems[0].parent() is newPlot
    assert newItems[1].parent() is newPlot
    assert newItems[2].parent() is newPlot
    assert newItems[0] is newItems[1].source()
    assert newItems[1] is newItems[2].source()
