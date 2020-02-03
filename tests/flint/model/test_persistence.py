"""Testing persistence of model.

This module check that anything stored in Redis can be read back. 
"""

import pickle
import pytest

from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.helper import style_helper


@pytest.mark.parametrize(
    "tested",
    [
        plot_model.Plot,
        plot_model.Item,
        plot_model.StyleStrategy,
        plot_model.ChannelRef,
        plot_item_model.CurvePlot,
        plot_item_model.ScatterPlot,
        plot_item_model.McaPlot,
        plot_item_model.ImagePlot,
        plot_item_model.CurveItem,
        plot_item_model.ScatterItem,
        plot_item_model.McaItem,
        plot_item_model.ImageItem,
        plot_item_model.DerivativeItem,
        plot_item_model.CurveStatisticMixIn,
        plot_item_model.MaxCurveItem,
        plot_item_model.MotorPositionMarker,
        style_helper.DefaultStyleStrategy,
        style_model.Style,
    ],
)
def test_dumps_loads(tested):
    o = tested()
    data = pickle.dumps(o)
    _ = pickle.loads(data)


def test_parenting():
    plot = plot_item_model.CurvePlot()
    item = plot_item_model.CurveItem(plot)
    plot.addItem(item)
    item2 = plot_item_model.CurveItem(plot)
    style = style_model.Style(colormapLut="viridis")
    item2.setCustomStyle(style)
    plot.addItem(item2)
    channel = plot_model.ChannelRef(plot, "foo")
    item.setXChannel(channel)

    data = pickle.dumps(plot)
    resultPlot = pickle.loads(data)

    resultItem = resultPlot.items()[0]
    resultItem2 = resultPlot.items()[1]
    resultChannel = resultItem.xChannel()

    assert resultItem.parent() is resultPlot
    assert resultItem2.parent() is resultPlot
    assert resultItem.plot() is resultPlot
    assert resultItem.customStyle() is None
    assert resultItem2.plot() is resultPlot
    assert resultItem2.customStyle() is not None
    assert resultItem2.customStyle().colormapLut == "viridis"
    assert resultChannel.name() == channel.name()
