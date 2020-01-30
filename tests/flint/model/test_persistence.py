"""Testing persistence of model.

This module check that anything stored in Redis can be read back. 
"""

import pickle
import pytest

from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_model
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
    ],
)
def test_dumps_loads(tested):
    o = tested()
    data = pickle.dumps(o)
    _ = pickle.loads(data)
