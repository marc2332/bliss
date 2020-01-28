"""Testing scatter plot."""

import pytest
import numpy

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt
from silx.gui.plot import items as silx_items

from bliss.flint.widgets.scatter_plot import ScatterPlotWidget
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.helper import style_helper


@pytest.mark.usefixtures("local_flint")
class TestScatterPlot(TestCaseQt):
    def create_scan(self):
        scan = scan_model.Scan()
        master = scan_model.Device(scan)
        master.setName("master")
        device = scan_model.Device(scan)
        device.setName("device")
        device.setMaster(master)
        channel = scan_model.Channel(device)
        channel.setName("chan-x")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan-y")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan-v1")
        channel.setType(scan_model.ChannelType.COUNTER)
        channel = scan_model.Channel(device)
        channel.setName("chan-v2")
        channel.setType(scan_model.ChannelType.COUNTER)
        scan.seal()
        return scan

    def create_plot_with_chanv1(self):
        plot = plot_item_model.ScatterPlot()
        channelx = plot_model.ChannelRef(plot, "chan-x")
        channely = plot_model.ChannelRef(plot, "chan-y")
        channelv = plot_model.ChannelRef(plot, "chan-v1")
        item = plot_item_model.ScatterItem(plot)
        item.setXChannel(channelx)
        item.setYChannel(channely)
        item.setValueChannel(channelv)
        plot.addItem(item)
        flint = self.create_flint_model()
        styleStrategy = style_helper.DefaultStyleStrategy(flint)
        plot.setStyleStrategy(styleStrategy)
        return plot

    def create_plot_with_chanv1_chanv2(self):
        plot = plot_item_model.ScatterPlot()
        channelx = plot_model.ChannelRef(plot, "chan-x")
        channely = plot_model.ChannelRef(plot, "chan-y")
        channelv1 = plot_model.ChannelRef(plot, "chan-v1")
        channelv2 = plot_model.ChannelRef(plot, "chan-v2")
        item = plot_item_model.ScatterItem(plot)
        item.setXChannel(channelx)
        item.setYChannel(channely)
        item.setValueChannel(channelv1)
        plot.addItem(item)
        item = plot_item_model.ScatterItem(plot)
        item.setXChannel(channelx)
        item.setYChannel(channely)
        item.setValueChannel(channelv2)
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
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        widget = ScatterPlotWidget()
        widget.setFlintModel(flint)
        widget.setPlotModel(plot)
        widget.show()

        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 1
        widget.close()

    def test_display_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-x").setData(data)
        array = numpy.arange(4) + 10
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(4) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)

        widget = ScatterPlotWidget()
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2
        widget.close()

    def test_item_visibility(self):
        # Create a plot with already existing data, then hide the item
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-x").setData(data)
        array = numpy.arange(4) + 10
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(4) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)

        widget = ScatterPlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2

        imageItem = list(plot.items())[0]
        imageItem.setVisible(False)
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 1

        imageItem = list(plot.items())[0]
        imageItem.setVisible(True)
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2
        widget.close()

    def test_update_data(self):
        # Create a plot with already existing data, then update the data
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-x").setData(data)
        array = numpy.arange(4) + 10
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(4) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)

        widget = ScatterPlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()

        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-x").setData(data)
        array = numpy.arange(4) + 10
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(4) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)
        scan._fireScanDataUpdated("chan-x", "master")
        scan._fireScanDataUpdated("chan-y", "master")
        scan._fireScanDataUpdated("chan-v1", "master")

        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2
        widget.close()

    def test_new_scan_with_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        # Display a scan without data
        widget = ScatterPlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 1

        # Provide a new scan with data
        scan2 = self.create_scan()
        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan2.getChannelByName("chan-x").setData(data)
        array = numpy.arange(4) + 10
        data = scan_model.Data(scan, array)
        scan2.getChannelByName("chan-y").setData(data)
        array = numpy.arange(4) + 100
        data = scan_model.Data(scan, array)
        scan2.getChannelByName("chan-v1").setData(data)

        widget.setScan(scan2)
        self.qWait(1000)

        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2
        widget.close()

    def test_new_scan_without_data(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        # Display a scan with data
        array = numpy.arange(4)
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-x").setData(data)
        array = numpy.arange(4) + 10
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(4) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)

        widget = ScatterPlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2

        # Provide a new scan without data
        scan2 = self.create_scan()
        widget.setScan(scan2)
        self.qWait(1000)
        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 1
        widget.close()

    def test_regular_rendering(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        style = style_model.Style(
            fillStyle=style_model.FillStyle.SCATTER_REGULAR_GRID,
            colormapLut="viridis",
            symbolStyle="o",
            symbolSize=6.0,
        )
        item = plot.items()[0]
        item.setCustomStyle(style)

        array = numpy.arange(16)
        data = scan_model.Data(scan, array // 4)
        scan.getChannelByName("chan-x").setData(data)
        data = scan_model.Data(scan, array % 4)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(16) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)

        widget = ScatterPlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)

        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2
        widget.close()

    def test_irregular_rendering(self):
        # Create a plot with already existing data
        scan = self.create_scan()
        plot = self.create_plot_with_chanv1()
        flint = self.create_flint_model()

        style = style_model.Style(
            fillStyle=style_model.FillStyle.SCATTER_IRREGULAR_GRID,
            colormapLut="viridis",
            symbolStyle="o",
            symbolSize=6.0,
        )
        item = plot.items()[0]
        item.setCustomStyle(style)

        array = numpy.arange(16)
        data = scan_model.Data(scan, array // 4)
        scan.getChannelByName("chan-x").setData(data)
        data = scan_model.Data(scan, array % 4)
        scan.getChannelByName("chan-y").setData(data)
        array = numpy.arange(16) + 100
        data = scan_model.Data(scan, array)
        scan.getChannelByName("chan-v1").setData(data)

        widget = ScatterPlotWidget()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        widget.setScan(scan)
        widget.setPlotModel(plot)
        widget.show()
        self.qWait(1000)

        silxPlot = widget._silxPlot()
        scatters = [o for o in silxPlot.getItems() if isinstance(o, silx_items.Scatter)]
        assert len(scatters) == 2
        widget.close()
