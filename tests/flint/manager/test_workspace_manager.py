"""Testing persistence of model.

This module check that anything stored in Redis can be read back. 
"""

import pickle
import pytest

from bliss.flint.manager import workspace_manager
from bliss.flint.model import flint_model
from bliss.flint.widgets import curve_plot
from bliss.flint.model import plot_model


@pytest.mark.parametrize(
    "tested",
    [
        b"\x80\x03cbliss.flint.model.plot_model\nPlot\nq\x00)Rq\x01}q\x02(X\x05\x00\x00\x00itemsq\x03]q\x04X\x0e\x00\x00\x00style_strategyq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_model\nItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04Nub."
        b"\x80\x03cbliss.flint.model.plot_model\nStyleStrategy\nq\x00)Rq\x01."
        b"\x80\x03cbliss.flint.model.plot_model\nChannelRef\nq\x00)Rq\x01}q\x02X\x0c\x00\x00\x00channel_nameq\x03Nsb."
        b"\x80\x03cbliss.flint.model.plot_item_model\nCurvePlot\nq\x00)Rq\x01}q\x02(X\x05\x00\x00\x00itemsq\x03]q\x04X\x0e\x00\x00\x00style_strategyq\x05NX\x0b\x00\x00\x00scan_storedq\x06\x89ub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nScatterPlot\nq\x00)Rq\x01}q\x02(X\x05\x00\x00\x00itemsq\x03]q\x04X\x0e\x00\x00\x00style_strategyq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nMcaPlot\nq\x00)Rq\x01}q\x02(X\x05\x00\x00\x00itemsq\x03]q\x04X\x0e\x00\x00\x00style_strategyq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nImagePlot\nq\x00)Rq\x01}q\x02(X\x05\x00\x00\x00itemsq\x03]q\x04X\x0e\x00\x00\x00style_strategyq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nCurveItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x06\x00\x00\x00y_axisq\x05X\x04\x00\x00\x00leftq\x06X\x01\x00\x00\x00xq\x07NX\x01\x00\x00\x00yq\x08Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nScatterItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x01\x00\x00\x00xq\x05NX\x01\x00\x00\x00yq\x06NX\x05\x00\x00\x00valueq\x07Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nMcaItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x03\x00\x00\x00mcaq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nImageItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x05\x00\x00\x00imageq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_state_model\nDerivativeItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x06\x00\x00\x00sourceq\x05NX\x06\x00\x00\x00y_axisq\x06X\x04\x00\x00\x00leftq\x07ub."
        b"\x80\x03cbliss.flint.model.plot_state_model\nGaussianFitItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x06\x00\x00\x00sourceq\x05NX\x06\x00\x00\x00y_axisq\x06X\x04\x00\x00\x00leftq\x07ub."
        b"\x80\x03cbliss.flint.model.plot_state_model\nCurveStatisticItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x06\x00\x00\x00sourceq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_state_model\nMinCurveItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x06\x00\x00\x00sourceq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_state_model\nMaxCurveItem\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04NX\x06\x00\x00\x00sourceq\x05Nub."
        b"\x80\x03cbliss.flint.model.plot_item_model\nMotorPositionMarker\nq\x00)Rq\x01}q\x02(X\x07\x00\x00\x00visibleq\x03\x88X\x05\x00\x00\x00styleq\x04Nub."
        b"\x80\x03cbliss.flint.helper.style_helper\nDefaultStyleStrategy\nq\x00)Rq\x01."
        b"\x80\x03cbliss.flint.model.style_model\nStyle\nq\x00(cbliss.flint.model.style_model\nLineStyle\nq\x01cbliss.flint.model.style_model\nDescriptiveValue\nq\x02NX\x07\x00\x00\x00No lineq\x03\x86q\x04\x81q\x05\x85q\x06Rq\x07NNNcbliss.flint.model.style_model\nSymbolStyle\nq\x08h\x02NX\t\x00\x00\x00No symbolq\t\x86q\n\x81q\x0b\x85q\x0cRq\rNNNcbliss.flint.model.style_model\nFillStyle\nq\x0eh\x02NX\x07\x00\x00\x00No fillq\x0f\x86q\x10\x81q\x11\x85q\x12Rq\x13tq\x14\x81q\x15."
    ],
)
def test_deserialization_model_v1(tested):
    """This serialized objects was used on 2020-02-27 just before the restart

    This test check that there is no regression with sorted object in Redis
    """
    data = pickle.loads(tested)


def test_dumps_loads__empty_workspace(local_flint):
    obj = workspace_manager.WorkspaceData()
    data = pickle.dumps(obj)
    _ = pickle.loads(data)


@pytest.mark.parametrize("with_plot", [True, False])
def test_dumps_loads__workspace(with_plot, local_flint):
    workspace = flint_model.Workspace()

    plot = plot_model.Plot()
    widget = curve_plot.CurvePlotWidget()
    widget.setPlotModel(plot)
    workspace.addWidget(widget)
    workspace.addPlot(plot)

    data = workspace_manager.WorkspaceData()
    data.setWorkspace(workspace, includePlots=with_plot)
    string = pickle.dumps(data)
    print("-----------------------------------")
    print(string)
    data2 = pickle.loads(string)

    workspace2 = flint_model.Workspace()
    data2.feedWorkspace(workspace2, None)
    assert len(workspace2.widgets()) == 1
    widget2 = workspace2.widgets()[0]
    assert isinstance(widget, curve_plot.CurvePlotWidget)
    if with_plot:
        assert len(workspace2.plots()) == 1
        assert widget2.plotModel() is not None
        assert widget2.plotModel() is workspace2.plots()[0]
    else:
        assert len(workspace2.plots()) == 0
        assert widget2.plotModel() is None


@pytest.mark.parametrize(
    "data_test",
    [
        (
            "empty",
            b"\x80\x03cbliss.flint.manager.workspace_manager\nWorkspaceData\nq\x00)\x81q\x01.",
        ),
        (
            "with_plot",
            b"\x80\x03cbliss.flint.manager.workspace_manager\nWorkspaceData\nq\x00)\x81q\x01(X"
            b"\x05\x00\x00\x00plotsq\x02}q\x03\x8a\x06\xd0\xe7\xcc\xb4\xf9\x7fc"
            b"bliss.flint.model.plot_model\nPlot\nq\x04)Rq\x05}q\x06(X\x05\x00\x00"
            b"\x00itemsq\x07]q\x08X\x0e\x00\x00\x00style_strategyq\tNubsX\x07\x00"
            b"\x00\x00widgetsq\n]q\x0bcbliss.flint.manager.workspace_manager\n"
            b"WidgetDescription\nq\x0c)\x81q\r}q\x0e(X\n\x00\x00\x00objectNameq"
            b"\x0fX\x00\x00\x00\x00q\x10X\x0b\x00\x00\x00windowTitleq\x11h\x10X"
            b"\t\x00\x00\x00classNameq\x12cbliss.flint.widgets.curve_plot\n"
            b"CurvePlotWidget\nq\x13X\x07\x00\x00\x00modelIdq\x14\x8a\x06\xd0\xe7"
            b"\xcc\xb4\xf9\x7fX\x06\x00\x00\x00configq\x15c"
            b"bliss.flint.widgets.plot_helper\nPlotConfiguration"
            b"\nq\x16)Rq\x17}q\x18(X\x10\x00\x00\x00interaction_modeq\x19X\x04\x00"
            b"\x00\x00zoomq\x1aX\x0c\x00\x00\x00refresh_modeq\x1bM\xf4\x01X\x0c\x00"
            b"\x00\x00x_axis_scaleq\x1cX\x06\x00\x00\x00linearq\x1dX\x0c\x00\x00"
            b"\x00y_axis_scaleq\x1eh\x1dX\r\x00\x00\x00y2_axis_scaleq\x1fh\x1dX\x0f"
            b"\x00\x00\x00y_axis_invertedq cnumpy.core.multiarray\nscalar\nq!cnumpy"
            b'\ndtype\nq"X\x02\x00\x00\x00b1q#K\x00K\x01\x87q$Rq%(K\x03X\x01\x00\x00'
            b"\x00|q&NNNJ\xff\xff\xff\xffJ\xff\xff\xff\xffK\x00tq'bC\x01\x00q(\x86q)Rq"
            b"*X\x10\x00\x00\x00y2_axis_invertedq+h*X\x12\x00\x00\x00fixed_aspect_ratio"
            b"q,\x89X\t\x00\x00\x00grid_modeq-NX\x0e\x00\x00\x00axis_displayedq.\x88X"
            b"\x11\x00\x00\x00crosshair_enabledq/\x89X\x12\x00\x00\x00colorbar_displayed"
            b"q0\x89X\x18\x00\x00\x00profile_widget_displayedq1\x89X\x14\x00\x00\x00"
            b"roi_widget_displayedq2\x89X\x1a\x00\x00\x00histogram_widget_displayed"
            b"q3\x89ububau.",
        ),
        (
            "without_plot",
            b"\x80\x03cbliss.flint.manager.workspace_manager\nWorkspaceData\nq\x00)"
            b"\x81q\x01(X\x05\x00\x00\x00plotsq\x02}q\x03X\x07\x00\x00\x00widgetsq"
            b"\x04]q\x05cbliss.flint.manager.workspace_manager\nWidgetDescription"
            b"\nq\x06)\x81q\x07}q\x08(X\n\x00\x00\x00objectNameq\tX\x00\x00\x00\x00"
            b"q\nX\x0b\x00\x00\x00windowTitleq\x0bh\nX\t\x00\x00\x00classNameq\x0c"
            b"cbliss.flint.widgets.curve_plot\nCurvePlotWidget\nq\rX\x07\x00\x00"
            b"\x00modelIdq\x0eNX\x06\x00\x00\x00configq\x0fcbliss.flint.widgets.plot_helper"
            b"\nPlotConfiguration\nq\x10)Rq\x11}q\x12(X\x10\x00\x00\x00interaction_modeq"
            b"\x13X\x04\x00\x00\x00zoomq\x14X\x0c\x00\x00\x00refresh_modeq\x15M\xf4"
            b"\x01X\x0c\x00\x00\x00x_axis_scaleq\x16X\x06\x00\x00\x00linearq\x17X\x0c"
            b"\x00\x00\x00y_axis_scaleq\x18h\x17X\r\x00\x00\x00y2_axis_scaleq\x19h"
            b"\x17X\x0f\x00\x00\x00y_axis_invertedq\x1acnumpy.core.multiarray\nscalar"
            b"\nq\x1bcnumpy\ndtype\nq\x1cX\x02\x00\x00\x00b1q\x1dK\x00K\x01\x87q\x1e"
            b"Rq\x1f(K\x03X\x01\x00\x00\x00|q NNNJ\xff\xff\xff\xffJ\xff\xff\xff\xff"
            b'K\x00tq!bC\x01\x00q"\x86q#Rq$X\x10\x00\x00\x00y2_axis_invertedq%h$X'
            b"\x12\x00\x00\x00fixed_aspect_ratioq&\x89X\t\x00\x00\x00grid_modeq'NX"
            b"\x0e\x00\x00\x00axis_displayedq(\x88X\x11\x00\x00\x00crosshair_enabled"
            b"q)\x89X\x12\x00\x00\x00colorbar_displayedq*\x89X\x18\x00\x00\x00"
            b"profile_widget_displayedq+\x89X\x14\x00\x00\x00roi_widget_displayed"
            b"q,\x89X\x1a\x00\x00\x00histogram_widget_displayedq-\x89ububau.",
        ),
    ],
)
def test_deserialization_workspace_v1(data_test, local_flint):
    """This serialized objects was used on 2020-02-27 just before the restart

    This test check that there is no regression with sorted object in Redis
    """
    name, string = data_test
    data = pickle.loads(string)

    if name == "empty":
        pass
    else:
        workspace = flint_model.Workspace()
        data.feedWorkspace(workspace, None)
        assert len(workspace.widgets()) == 1
        widget = workspace.widgets()[0]
        assert isinstance(widget, curve_plot.CurvePlotWidget)
        if name == "with_plot":
            assert len(workspace.plots()) == 1
            assert widget.plotModel() is not None
            assert widget.plotModel() is workspace.plots()[0]
        else:
            assert len(workspace.plots()) == 0
            assert widget.plotModel() is None

    print(pickle.dumps(data))
