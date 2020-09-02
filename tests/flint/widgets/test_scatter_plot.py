"""Testing scatter plot."""

import pytest
import numpy

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt
from silx.gui.plot import items as silx_items

from bliss.common.scans.scan_info import ScanInfoFactory

from bliss.flint.widgets.scatter_plot import ScatterPlotWidget
from bliss.flint.widgets.scatter_plot import ScatterNormalization
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.helper import style_helper
from bliss.flint.helper import scan_info_helper


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


def test_scatter_normalization__normal():
    scan_info = {"acquisition_chain": {"timer": {"scalars": ["a", "b", "c"]}}}
    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta("a", axis_id=0, axis_points=3, axis_kind="forth")
    factory.set_channel_meta("b", axis_id=1, axis_points=3, axis_kind="forth")
    factory.add_scatter_plot("foo", x="a", y="b", value="c")
    scan = scan_info_helper.create_scan_model(scan_info, False)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    item = plots[0].items()[0]
    scatterSize = 8
    normalizer = ScatterNormalization(scan, item, scatterSize)
    assert not normalizer.hasNormalization()
    indexes = numpy.arange(scatterSize, dtype=int)
    indexes = normalizer.normalize(indexes)
    expected = numpy.arange(scatterSize, dtype=int)
    numpy.testing.assert_allclose(indexes, expected)


def test_scatter_normalization__normal_frame():
    scan_info = {"acquisition_chain": {"timer": {"scalars": ["a", "b", "c", "d"]}}}
    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta("a", axis_id=0, axis_points=3, axis_kind="forth")
    factory.set_channel_meta("b", axis_id=1, axis_points=3, axis_kind="forth")
    factory.set_channel_meta("c", axis_id=2, axis_points=3, axis_kind="step")
    factory.add_scatter_plot("foo", x="a", y="b", value="d")
    scan = scan_info_helper.create_scan_model(scan_info, False)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    plot = plots[0]
    item = plot.items()[0]
    item.setGroupByChannels([plot_model.ChannelRef(plot, "c")])
    c = numpy.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2])
    scatterSize = len(c)
    scan.getChannelByName("c").setData(scan_model.Data(scan, c))
    normalizer = ScatterNormalization(scan, item, scatterSize)
    indexes = numpy.arange(scatterSize, dtype=int)
    indexes = normalizer.normalize(indexes)
    expected = numpy.arange(scatterSize, dtype=int)[9 * 2 :]
    numpy.testing.assert_allclose(indexes, expected)


def test_scatter_normalization__backnforth():
    scan_info = {"acquisition_chain": {"timer": {"scalars": ["a", "b", "c", "d"]}}}
    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta(
        "a", axis_id=0, axis_points=3, group="g", axis_kind="backnforth"
    )
    factory.set_channel_meta(
        "b", axis_id=1, axis_points=3, group="g", axis_kind="forth"
    )
    factory.add_scatter_plot("foo", x="a", y="b", value="d")
    scan = scan_info_helper.create_scan_model(scan_info, False)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    plot = plots[0]
    item = plot.items()[0]
    scatterSize = 7
    normalizer = ScatterNormalization(scan, item, scatterSize)
    xChannel = item.xChannel().channel(scan)
    yChannel = item.yChannel().channel(scan)
    assert normalizer.isImageRenderingSupported(xChannel, yChannel)
    indexes = numpy.arange(scatterSize, dtype=int)
    indexes = normalizer.normalize(indexes)
    expected = [0, 1, 2, 5, 4, 3, 6, numpy.nan, numpy.nan]
    numpy.testing.assert_allclose(indexes, expected)


def test_scatter_normalization__3d_backnforth():
    scan_info = {"acquisition_chain": {"timer": {"scalars": ["a", "b", "c", "d"]}}}
    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta(
        "a", axis_id=0, axis_points=2, group="g", axis_kind="backnforth"
    )
    factory.set_channel_meta(
        "b", axis_id=1, axis_points=3, group="g", axis_kind="backnforth"
    )
    factory.set_channel_meta(
        "c", axis_id=2, axis_points=4, group="g", axis_kind="forth"
    )
    factory.add_scatter_plot("foo", x="a", y="b", value="d")
    scan = scan_info_helper.create_scan_model(scan_info, False)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    plot = plots[0]
    item = plot.items()[0]
    scatterSize = 15
    normalizer = ScatterNormalization(scan, item, scatterSize)
    xChannel = item.xChannel().channel(scan)
    yChannel = item.yChannel().channel(scan)
    assert normalizer.isImageRenderingSupported(xChannel, yChannel)
    indexes = numpy.arange(scatterSize, dtype=int)
    indexes = normalizer.normalize(indexes)
    expected = [
        0,
        1,
        3,
        2,
        4,
        5,
        11,
        10,
        8,
        9,
        7,
        6,
        12,
        13,
        numpy.nan,
        14,
        numpy.nan,
        numpy.nan,
        numpy.nan,
        numpy.nan,
        numpy.nan,
        numpy.nan,
        numpy.nan,
        numpy.nan,
    ]
    numpy.testing.assert_allclose(indexes, expected)
