"""Testing time curve plot."""

import pytest

from silx.gui import qt

from bliss.flint.custom_plots import time_curve_plot


@pytest.fixture(scope="function")
def time_curve_plot_widget(local_flint):
    w = time_curve_plot.TimeCurvePlot()
    w.setAttribute(qt.Qt.WA_DeleteOnClose)
    w.setVisible(True)
    yield w
    w.close()


def test_time_curve_plot__creation(time_curve_plot_widget):
    """The widget can be implemented"""
    pass


def test_time_curve_plot__set_data(time_curve_plot_widget):
    """The setData of the widget can be used

    We expect curves to be displayed
    """
    w = time_curve_plot_widget
    w.addTimeCurveItem("value1")
    w.addTimeCurveItem("value2")
    w.setData(
        time=[0, 1, 2, 3, 4, 5], value1=[0, 1, 2, 3, 4, 5], value2=[0, 1, 2, 3, 4, 5]
    )
    plot = w.getPlotWidget()
    assert len(plot.getAllCurves()) == 2


def test_time_curve_plot__clear(time_curve_plot_widget):
    """Feed a plot and call `clear`

    We expect no curves to be displayed
    """
    w = time_curve_plot_widget
    w.addTimeCurveItem("value1")
    w.addTimeCurveItem("value2")
    w.setData(
        time=[0, 1, 2, 3, 4, 5], value1=[0, 1, 2, 3, 4, 5], value2=[0, 1, 2, 3, 4, 5]
    )
    w.clear()
    plot = w.getPlotWidget()
    assert len(plot.getAllCurves()) == 0


def test_time_curve_plot__append_data(time_curve_plot_widget):
    """Create a plot and feed data with `appendData`

    We expect the plot to contains curves witch grow up.
    """
    w = time_curve_plot_widget
    w.addTimeCurveItem("value1")
    w.addTimeCurveItem("value2")
    w.appendData(time=[0, 1, 2], value1=[0, 1, 2], value2=[0, 1, 2])
    plot = w.getPlotWidget()
    curve = plot.getAllCurves()[0]
    assert len(curve.getXData()) == 3
    w.appendData(time=[3, 4, 5], value1=[0, 1, 2], value2=[0, 1, 2])
    curve = plot.getAllCurves()[0]
    assert len(curve.getXData()) == 6


def test_time_curve_plot__drop_data(time_curve_plot_widget):
    """Create a plot with limited life time data duration and feed it with data

    We expect the plot to contain curves witch grow up on one side, and disappear
    on the other side.
    """
    w = time_curve_plot_widget
    w.setXDuration(5)
    w.addTimeCurveItem("value1")
    w.addTimeCurveItem("value2")
    w.appendData(time=[0, 1, 2], value1=[0, 1, 2], value2=[0, 1, 2])
    w.appendData(time=[3, 4, 5], value1=[0, 1, 2], value2=[0, 1, 2])
    w.appendData(time=[6, 7, 8], value1=[0, 1, 2], value2=[0, 1, 2])
    plot = w.getPlotWidget()
    curve = plot.getAllCurves()[0]
    assert len(curve.getXData()) <= 5 + 2
    assert curve.getXData()[0] > 0
    assert curve.getXData()[-1] == 8
