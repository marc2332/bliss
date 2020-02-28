"""Testing image plot."""

import pytest
import numpy

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt

from bliss.flint.widgets.image_plot import ImagePlotWidget
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.helper import style_helper


@pytest.mark.usefixtures("local_flint")
class TestImagePlot(TestCaseQt):

    NB_PERMANENT_ITEM = 3

    def create_scan(self):
        scan = scan_model.Scan()
        master = scan_model.Device(scan)
        master.setName("master")
        device = scan_model.Device(scan)
        device.setName("device")
        device.setMaster(master)
        channel = scan_model.Channel(device)
        channel.setName("chan1")
        channel.setType(scan_model.ChannelType.IMAGE)
        channel = scan_model.Channel(device)
        channel.setName("chan2")
        channel.setType(scan_model.ChannelType.IMAGE)
        scan.seal()
        return scan

    def create_plot_with_chan1(self):
        plot = plot_item_model.ImagePlot()
        item = plot_item_model.ImageItem(plot)
        channel = plot_model.ChannelRef(plot, "chan1")
        item.setImageChannel(channel)
        plot.addItem(item)
        flint = self.create_flint_model()
        styleStrategy = style_helper.DefaultStyleStrategy(flint)
        plot.setStyleStrategy(styleStrategy)
        return plot

    def create_plot_with_chan2(self):
        plot = plot_item_model.ImagePlot()
        item = plot_item_model.ImageItem(plot)
        channel = plot_model.ChannelRef(plot, "chan2")
        item.setImageChannel(channel)
        plot.addItem(item)
        flint = self.create_flint_model()
        styleStrategy = style_helper.DefaultStyleStrategy(flint)
        plot.setStyleStrategy(styleStrategy)
        return plot

    def create_plot_with_chan1_chan2(self):
        plot = plot_item_model.ImagePlot()
        item = plot_item_model.ImageItem(plot)
        channel = plot_model.ChannelRef(plot, "chan1")
        item.setImageChannel(channel)
        plot.addItem(item)
        channel = plot_model.ChannelRef(plot, "chan2")
        item.setImageChannel(channel)
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

        widget = ImagePlotWidget()
        widget.setFlintModel(flint)
        widget.setPlotModel(plot)
        widget.show()

        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) == self.NB_PERMANENT_ITEM
        widget.close()

    def test_display_image(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)

        widget = ImagePlotWidget()
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        silxPlot = widget._silxPlot()
        self.qWait(1000)
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM
        widget.close()

    def test_image_visibility(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)

        widget = ImagePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM

        imageItem = list(plot.items())[0]
        imageItem.setVisible(False)
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) == self.NB_PERMANENT_ITEM

        imageItem = list(plot.items())[0]
        imageItem.setVisible(True)
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM
        widget.close()

    def test_update_image(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)

        widget = ImagePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        scan._fireScanDataUpdated("chan1", "master")

        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM
        widget.close()

    def test_new_scan_with_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        # Display a scan without data
        flint.setCurrentScan(scan)
        widget = ImagePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) == self.NB_PERMANENT_ITEM

        # Provide a new scan with data
        scan2 = self.create_scan()
        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan2, array)
        scan2.getChannelByName("chan1").setData(data)
        widget.setScan(scan2)
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM
        widget.close()

    def test_new_scan_without_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()

        # Display a scan with data
        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        widget = ImagePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM

        # Provide a new scan without data
        scan2 = self.create_scan()
        widget.setScan(scan2)
        silxPlot = widget._silxPlot()
        self.qWait(1000)
        # The previous image is still displayed
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM

        # Until the end of the scan
        scan2.scanFinished.emit()
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) == self.NB_PERMANENT_ITEM

        widget.close()

    def test_display_image_2(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chan1_chan2()
        flint = self.create_flint_model()

        array = numpy.arange(4).reshape(2, 2)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan1").setData(data)
        array = numpy.arange(9).reshape(3, 3)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan2").setData(data)

        widget = ImagePlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        silxPlot = widget._silxPlot()
        assert len(silxPlot.getItems()) > self.NB_PERMANENT_ITEM
        widget.close()

    def test_refresh_propagation__update_scan(self):
        scan1 = self.create_scan()
        scan2 = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()
        channel1 = scan1.getChannelByName("chan1")
        channel2 = scan2.getChannelByName("chan1")

        widget = ImagePlotWidget()
        widget.setFlintModel(flint)
        widget.setScan(scan1)
        widget.setPlotModel(plot)

        # Initial state
        rate = widget.getRefreshManager().refreshMode()
        assert channel1.preferedRefreshRate() == rate
        assert channel2.preferedRefreshRate() is None

        # Change the scan
        widget.setScan(scan2)
        assert channel1.preferedRefreshRate() is None
        assert channel2.preferedRefreshRate() == rate

        self.qWait(1000)
        widget.close()

    def test_refresh_propagation__update_plot(self):
        scan = self.create_scan()
        plot1 = self.create_plot_with_chan1()
        plot2 = self.create_plot_with_chan2()
        flint = self.create_flint_model()
        channel1 = scan.getChannelByName("chan1")
        channel2 = scan.getChannelByName("chan2")

        widget = ImagePlotWidget()
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot1)

        # Initial state
        rate = widget.getRefreshManager().refreshMode()
        assert channel1.preferedRefreshRate() == rate
        assert channel2.preferedRefreshRate() is None

        # Change the plot
        widget.setPlotModel(plot2)
        assert channel1.preferedRefreshRate() is None
        assert channel2.preferedRefreshRate() == rate

        # Update the plot content
        item = plot2.items()[0]
        plot2.removeItem(item)
        self.qWait(1000)
        assert channel2.preferedRefreshRate() is None
        plot2.addItem(item)
        self.qWait(1000)
        assert channel2.preferedRefreshRate() == rate

        widget.close()

    def test_refresh_propagation__update_rate(self):
        scan = self.create_scan()
        plot = self.create_plot_with_chan1()
        flint = self.create_flint_model()
        channel = scan.getChannelByName("chan1")

        widget = ImagePlotWidget()
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)

        rate = widget.getRefreshManager().refreshMode()
        newRate = rate + 100
        assert channel.preferedRefreshRate() != newRate
        widget.getRefreshManager().setRefreshMode(newRate)
        assert channel.preferedRefreshRate() == newRate

        widget.close()
