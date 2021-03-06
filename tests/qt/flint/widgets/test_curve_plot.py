"""Testing image plot."""

import pytest
import numpy

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt

from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.helper import style_helper


@pytest.mark.usefixtures("local_flint")
class TestCurvePlot(TestCaseQt):

    NB_PERMANENT_ITEM = 3

    def nbItems(self, widget):
        silxPlot = widget._silxPlot()
        return len(silxPlot.getItems()) - self.NB_PERMANENT_ITEM

    def create_scan(self):
        scan = scan_model.Scan()
        master = scan_model.Device(scan)
        master.setName("master")
        device = scan_model.Device(scan)
        device.setName("device")
        device.setMaster(master)
        channel = scan_model.Channel(device)
        channel.setName("chan1")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan2")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan-x")
        channel.setType(scan_model.ChannelType.COUNTER)
        scan.seal()
        return scan

    def create_plot_with_chan1(self):
        plot = plot_item_model.CurvePlot()
        item = plot_item_model.CurveItem(plot)
        channel = plot_model.ChannelRef(plot, "chan1")
        item.setYChannel(channel)
        channel = plot_model.ChannelRef(plot, "chan-x")
        item.setXChannel(channel)
        plot.addItem(item)
        flint = self.create_flint_model()
        styleStrategy = style_helper.DefaultStyleStrategy(flint)
        plot.setStyleStrategy(styleStrategy)
        return plot

    def create_plot_with_chan1_chan2(self):
        plot = plot_item_model.CurvePlot()
        item = plot_item_model.CurveItem(plot)
        channel = plot_model.ChannelRef(plot, "chan1")
        item.setYChannel(channel)
        channel = plot_model.ChannelRef(plot, "chan-x")
        item.setXChannel(channel)
        plot.addItem(item)
        channel = plot_model.ChannelRef(plot, "chan2")
        item.setYChannel(channel)
        channel = plot_model.ChannelRef(plot, "chan-x")
        item.setXChannel(channel)
        plot.addItem(item)
        flint = self.create_flint_model()
        styleStrategy = style_helper.DefaultStyleStrategy(flint)
        plot.setStyleStrategy(styleStrategy)
        return plot

    def create_flint_model(self):
        flint = flint_model.FlintState()
        return flint

    def test_display_nothing(self):
        # Create a plot with already existing data
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        widget = CurvePlotWidget()
        self.nbItems(widget)
        widget.setFlintModel(flint)
        widget.setPlotModel(plot)
        self.nbItems(widget)
        widget.show()

        self.qWait(1000)

        assert self.nbItems(widget) == 0
        widget.close()

    def test_display_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan.getChannelByName("chan-x").setData(data)

        widget = CurvePlotWidget()
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        self.qWait(1000)
        assert self.nbItems(widget) == 1

        widget.close()

    def test_data_visibility(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan.getChannelByName("chan-x").setData(data)

        widget = CurvePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)
        assert self.nbItems(widget) == 1

        imageItem = list(plot.items())[0]
        imageItem.setVisible(False)
        self.qWait(1000)
        assert self.nbItems(widget) == 0

        imageItem = list(plot.items())[0]
        imageItem.setVisible(True)
        self.qWait(1000)
        assert self.nbItems(widget) == 1
        widget.close()

    def test_update_data(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan.getChannelByName("chan-x").setData(data)

        widget = CurvePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan.getChannelByName("chan-x").setData(data)
        scan._fireScanDataUpdated("chan1", "master")

        self.qWait(1000)
        assert self.nbItems(widget) == 1
        widget.close()

    def test_new_scan_with_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        # Display a scan without data
        widget = CurvePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)
        assert self.nbItems(widget) == 0

        # Provide a new scan with data
        scan2 = self.create_scan()
        array = numpy.arange(4)
        data = scan_model.Data(scan2, array)
        scan2.getChannelByName("chan1").setData(data)
        scan2.getChannelByName("chan-x").setData(data)
        widget.setScan(scan2)
        self.qWait(1000)
        assert self.nbItems(widget) == 1
        widget.close()

    def test_new_scan_without_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        # Display a scan with data
        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan.getChannelByName("chan-x").setData(data)
        widget = CurvePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)
        assert self.nbItems(widget) == 1

        # Provide a new scan without data
        scan2 = self.create_scan()
        widget.setScan(scan2)
        self.qWait(1000)
        assert self.nbItems(widget) == 0
        widget.close()

    def test_display_data_2(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1_chan2()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan.getChannelByName("chan-x").setData(data)
        array = 4 - numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan2").setData(data)

        widget = CurvePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        assert self.nbItems(widget) == 1
        widget.close()
