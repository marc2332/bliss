"""Testing curve stack."""

import pytest
import numpy
import scipy.signal

from silx.gui import qt

from bliss.flint.custom_plots import curve_stack


@pytest.fixture(scope="function")
def curve_stack_widget(qapp):
    w = curve_stack.CurveStack()
    w.setAttribute(qt.Qt.WA_DeleteOnClose)
    w.setVisible(True)
    yield w
    w.close()


def test_curve_stack__creation(curve_stack_widget):
    pass


def test_curve_stack__set_data(curve_stack_widget):
    w = curve_stack_widget
    data = numpy.empty((10, 100))
    for i in range(10):
        data[i] = scipy.signal.gaussian(100, i + 0.5)
        data[i][0] = i

    x = numpy.arange(100) * 10
    w.setData(data, x)
    plot = w.getPlotWidget()
    assert len(plot.getAllCurves()) == 1


def test_curve_stack__clear(curve_stack_widget):
    w = curve_stack_widget
    data = numpy.empty((10, 100))
    x = numpy.arange(100) * 10
    w.setData(data, x)
    w.clear()
    plot = w.getPlotWidget()
    assert len(plot.getAllCurves()) == 0


def test_curve_stack__set_selection(curve_stack_widget):
    w = curve_stack_widget
    data = numpy.empty((10, 100))
    for i in range(10):
        data[i] = scipy.signal.gaussian(100, i + 0.5)
        data[i][0] = i

    x = numpy.arange(100) * 10
    w.setData(data, x)
    assert w.selection() == 0

    plot = w.getPlotWidget()

    w.setSelection(5)
    assert w.selection() == 5
    curves = plot.getAllCurves()
    assert len(curves) == 1
    assert curves[0][1][0] == 5

    w.setSelection(6)
    assert w.selection() == 6
    curves = plot.getAllCurves()
    assert len(curves) == 1
    assert curves[0][1][0] == 6
