"""Testing manager module."""

import copy
from bliss.flint.manager.manager import ManageMainBehaviours
from bliss.flint.model import flint_model
from bliss.flint.model import plot_item_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from tests.qt.flint.factory import ScanInfoFactory


def _create_loopscan_scan_info():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0, unit="s")
    factory.add_channel(channel_id="timer:epoch", dim=0, unit="s")
    factory.add_device(root_id="timer", device_id="diode", triggered_by="timer")
    factory.add_channel(channel_id="diode:diode1", dim=0)
    factory.add_channel(channel_id="diode:diode2", dim=0)
    factory["type"] = "loopscan"
    return factory.scan_info()


def _create_ascan_scan_info(master_name, extra_name=None):
    factory = ScanInfoFactory()
    factory.add_device(root_id="ascan", device_id="master")
    factory.add_channel(channel_id=master_name, device_id="master", dim=0)

    factory.add_device(root_id="ascan", device_id="slave", triggered_by="master")
    factory.add_channel(
        channel_id="timer:elapsed_time", device_id="slave", dim=0, unit="s"
    )
    factory.add_channel(channel_id="timer:epoch", device_id="slave", dim=0, unit="s")
    factory.add_channel(channel_id="diode:diode1", device_id="slave", dim=0)
    factory.add_channel(channel_id="diode:diode2", device_id="slave", dim=0)
    if extra_name is not None:
        factory.add_channel(channel_id=extra_name, device_id="master", dim=0)
    factory["type"] = "ascan"
    return factory.scan_info()


def _create_lima_scan_info(include_roi2):
    """
    Simulate a scan containing a lima detector with ROIs.
    """
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)

    rois = {"roi1": {"kind": "rect", "x": 190, "y": 110, "width": 600, "height": 230}}
    if include_roi2:
        rois["roi2"] = {
            "kind": "arc",
            "cx": 487.0,
            "cy": 513.0,
            "r1": 137.0,
            "r2": 198.0,
            "a1": -172.0,
            "a2": -300.0,
        }
    factory.add_lima_device(
        device_id="beamviewer",
        root_id="timer",
        triggered_by="timer",
        image=True,
        rois=rois,
    )
    factory.add_channel(channel_id="beamviewer:roi_counters:roi1_sum", dim=0)
    if include_roi2:
        factory.add_channel(channel_id="beamviewer:roi_counters:roi2_sum", dim=0)

    scan_info = factory.scan_info()
    return scan_info


def test_curve_plot__from_loopscan_to_ascan(local_flint):
    """
    Test plot state with consecutive scans

    - Create a loopscan -> elapsed_time should be the axis
    - Then create a ascan -> the motor should be the axis
    """
    flint = flint_model.FlintState()
    workspace = flint_model.Workspace()
    flint.setWorkspace(workspace)
    widget = CurvePlotWidget()
    workspace.addWidget(widget)

    manager = ManageMainBehaviours()
    manager.setFlintModel(flint)

    loopscan_info = _create_loopscan_scan_info()
    scan = scan_info_helper.create_scan_model(loopscan_info)
    plots = scan_info_helper.create_plot_model(loopscan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    ascan_info = _create_ascan_scan_info("axis:sx")
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    model = widget.plotModel()
    item = model.items()[0]
    assert item.xChannel().name() == "axis:sx"


def test_curve_plot__user_selection(local_flint):
    """
    Test plot state with consecutive scans and a user selection in between

    We expect the user selection to be restored
    """
    flint = flint_model.FlintState()
    workspace = flint_model.Workspace()
    flint.setWorkspace(workspace)
    widget = CurvePlotWidget()
    workspace.addWidget(widget)

    manager = ManageMainBehaviours()
    manager.setFlintModel(flint)

    loopscan_info = _create_loopscan_scan_info()
    scan = scan_info_helper.create_scan_model(loopscan_info)
    plots = scan_info_helper.create_plot_model(loopscan_info, scan)
    plot = [p for p in plots if isinstance(p, plot_item_model.CurvePlot)][0]
    manager.updateWidgetWithPlot(widget, scan, plot, useDefaultPlot=False)
    model = widget.plotModel()
    assert len(model.items()) == 1

    # user selection
    model_helper.updateDisplayedChannelNames(
        plot, scan, ["diode:diode1", "diode:diode2"]
    )
    plot.tagUserEditTime()

    ascan_info = _create_ascan_scan_info("axis:sx")
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    plot = [p for p in plots if isinstance(p, plot_item_model.CurvePlot)][0]
    manager.updateWidgetWithPlot(widget, scan, plot, useDefaultPlot=False)

    model = widget.plotModel()
    assert len(model.items()) == 2


def test_curve_plot__ascan_axis_updated(local_flint):
    """
    Test plot state with consecutive scans

    - Create a ascan -> sx should be the axis
    - Then create a ascan -> sy should be the axis
    """
    flint = flint_model.FlintState()
    workspace = flint_model.Workspace()
    flint.setWorkspace(workspace)
    widget = CurvePlotWidget()
    workspace.addWidget(widget)

    manager = ManageMainBehaviours()
    manager.setFlintModel(flint)

    ascan_info = _create_ascan_scan_info("axis:sx", "axis:sy")
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    model = widget.plotModel()
    item = model.items()[0]
    assert item.xChannel().name() == "axis:sx"

    ascan_info = _create_ascan_scan_info("axis:sy", "axis:sx")
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    model = widget.plotModel()
    item = model.items()[0]
    assert item.xChannel().name() == "axis:sy"


def test_curve_plot__enforced_channel_from_scan_info(local_flint):
    """
    Test a new plot with enforced channel (plotinit)

    We expect the channel from the scan_info to be used,
    anyway the user selection was done on the previous plot
    """
    flint = flint_model.FlintState()
    workspace = flint_model.Workspace()
    flint.setWorkspace(workspace)
    widget = CurvePlotWidget()
    workspace.addWidget(widget)

    manager = ManageMainBehaviours()
    manager.setFlintModel(flint)

    ascan_info = _create_ascan_scan_info("axis:sx", "axis:sy")
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    enforced_channel = "axis:sy"

    # Enforce a user selection
    plotModel = widget.plotModel()
    plotModel.tagUserEditTime()
    item = plotModel.items()[0]
    # Make sure the following test have meaning
    assert item.yChannel().name() != enforced_channel

    ascan_info = _create_ascan_scan_info("axis:sy", "axis:sx")
    ascan_info["_display_extra"] = {"displayed_channels": [enforced_channel]}
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    plotModel = widget.plotModel()
    item = plotModel.items()[0]
    assert item.yChannel().name() == enforced_channel


def test_image_plot_with_new_roi(local_flint):
    """Test the resulted image plot when a new ROI is part of the scan.

    We expect:
    - The previous ROI to still use the same config
    - The new ROI to be displayed.
    """
    flint = flint_model.FlintState()
    workspace = flint_model.Workspace()
    flint.setWorkspace(workspace)
    widget = CurvePlotWidget()
    workspace.addWidget(widget)

    manager = ManageMainBehaviours()
    manager.setFlintModel(flint)

    scan_info1 = _create_lima_scan_info(include_roi2=False)
    scan = scan_info_helper.create_scan_model(scan_info1)
    plots = scan_info_helper.create_plot_model(scan_info1, scan)
    plot = [p for p in plots if isinstance(p, plot_item_model.ImagePlot)][0]
    manager.updateWidgetWithPlot(widget, scan, plot, useDefaultPlot=True)

    plotModel = widget.plotModel()
    assert len(plotModel.items()) == 2  # image + ROI

    roiItem = [i for i in plotModel.items() if isinstance(i, plot_item_model.RoiItem)][
        0
    ]
    roiItem.setVisible(False)

    scan_info2 = _create_lima_scan_info(include_roi2=True)
    scan = scan_info_helper.create_scan_model(scan_info2)
    plots = scan_info_helper.create_plot_model(scan_info2, scan)
    plot = [p for p in plots if isinstance(p, plot_item_model.ImagePlot)][0]
    manager.updateWidgetWithPlot(widget, scan, plot, useDefaultPlot=True)

    plotModel = widget.plotModel()
    assert len(plotModel.items()) == 3  # image + ROI * 2

    roiItems = [i for i in plotModel.items() if isinstance(i, plot_item_model.RoiItem)]
    rois = {r.name(): r.isVisible() for r in roiItems}
    assert rois == {"roi1": False, "roi2": True}
