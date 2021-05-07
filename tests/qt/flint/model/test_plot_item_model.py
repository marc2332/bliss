"""Testing plot item model."""

import numpy
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.model import plot_model
from bliss.flint.model import scan_model


def test_picklable():
    plot = plot_item_model.CurvePlot()
    plot.setScansStored(True)

    item = plot_item_model.CurveItem(plot)
    item.setXChannel(plot_model.ChannelRef(None, "x"))
    item.setYChannel(plot_model.ChannelRef(None, "y"))
    plot.addItem(item)

    item2 = plot_state_model.DerivativeItem(plot)
    item2.setYAxis("right")
    item2.setSource(item)
    plot.addItem(item2)

    item3 = plot_state_model.MaxCurveItem(plot)
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


def test_XIndexCurveItem():
    scan = scan_model.Scan()
    device = scan_model.Device(scan)
    channel = scan_model.Channel(device)
    channel.setName("y")
    channel.setType(scan_model.ChannelType.SPECTRUM)
    scan.seal()

    channel.setData(scan_model.Data(array=numpy.ones(3)))

    plot = plot_item_model.OneDimDataPlot()
    item = plot_item_model.XIndexCurveItem(plot)
    item.setYChannel(plot_model.ChannelRef(None, "y"))

    assert item.isValid()
    numpy.testing.assert_array_equal(item.yData(scan).array(), [1, 1, 1])
    numpy.testing.assert_array_equal(item.xData(scan).array(), [0, 1, 2])


def test_XConstCurveItem():
    scan = scan_model.Scan()
    device = scan_model.Device(scan)
    channel = scan_model.Channel(device)
    channel.setName("y")
    channel.setType(scan_model.ChannelType.SPECTRUM)
    scan.seal()

    channel.setData(scan_model.Data(array=numpy.ones(3)))

    plot = plot_item_model.OneDimDataPlot()
    item = plot_item_model.XConstCurveItem(plot)
    item.setYChannel(plot_model.ChannelRef(None, "y"))
    item.setXArray(numpy.array([0, 1, 4]))

    assert item.isValid()
    numpy.testing.assert_array_equal(item.yData(scan).array(), [1, 1, 1])
    numpy.testing.assert_array_equal(item.xData(scan).array(), [0, 1, 4])
