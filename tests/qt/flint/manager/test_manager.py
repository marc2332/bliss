"""Testing manager module."""

import copy
from bliss.flint.manager.manager import ManageMainBehaviours
from bliss.flint.model import flint_model
from bliss.flint.model import plot_item_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.helper import scan_info_helper


SCAN_INFO_LIMA_ROIS = {
    "acquisition_chain": {
        "timer": {"devices": ["timer", "beamviewer", "beamviewer:roi_counters"]}
    },
    "devices": {
        "timer": {
            "channels": ["timer:elapsed_time", "timer:epoch"],
            "triggered_devices": ["beamviewer"],
        },
        "beamviewer": {
            "type": "lima",
            "triggered_devices": ["beamviewer:roi_counters"],
            "channels": ["beamviewer:image"],
        },
        "beamviewer:roi_counters": {
            "channels": [
                "beamviewer:roi_counters:roi1_sum",
                "beamviewer:roi_counters:roi2_sum",
            ],
            "roi1": {"kind": "rect", "x": 190, "y": 110, "width": 600, "height": 230},
            "roi2": {
                "kind": "arc",
                "cx": 487.0,
                "cy": 513.0,
                "r1": 137.0,
                "r2": 198.0,
                "a1": -172.0,
                "a2": -300.0,
            },
        },
    },
    "channels": {
        "timer:elapsed_time": {"dim": 0},
        "timer:epoch": {"dim": 0},
        "beamviewer:roi_counters:roi1_sum": {"dim": 0},
        "beamviewer:roi_counters:roi2_sum": {"dim": 0},
        "beamviewer:image": {"dim": 2},
    },
}


def _create_ascan_scan_info(master_name, extra_name=None):
    result = {
        "type": "ascan",
        "acquisition_chain": {"main": {"devices": ["master", "slave"]}},
        "devices": {
            "master": {"channels": [master_name], "triggered_devices": ["slave"]},
            "slave": {
                "channels": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "simulation_diode_sampling_controller:diode1",
                    "simulation_diode_sampling_controller:diode2",
                ]
            },
        },
        "channels": {
            master_name: {"dim": 0},
            "timer:elapsed_time": {"dim": 0},
            "timer:epoch": {"dim": 0},
            "simulation_diode_sampling_controller:diode1": {"dim": 0},
            "simulation_diode_sampling_controller:diode2": {"dim": 0},
        },
    }
    if extra_name is not None:
        result["devices"]["slave"]["channels"].append(extra_name)
        result["channels"][extra_name] = {"dim": 0}
    return result


def _create_lima_scan_info(include_roi2):
    """
    Simulate a scan containing a lima detector with ROIs.
    """
    result = copy.deepcopy(SCAN_INFO_LIMA_ROIS)
    if not include_roi2:
        del result["devices"]["beamviewer:roi_counters"]["roi2"]
    return result


def test_consecutive_scans__loopscan_ascan(local_flint):
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

    loopscan_info = {
        "type": "loopscan",
        "acquisition_chain": {"main": {"devices": ["master", "slave"]}},
        "devices": {
            "master": {
                "channels": ["timer:elapsed_time", "timer:epoch"],
                "triggered_devices": ["slave"],
            },
            "slave": {"channels": ["simulation_diode_sampling_controller:diode1"]},
        },
        "channels": {
            "timer:elapsed_time": {"dim": 0},
            "timer:epoch": {"dim": 0},
            "simulation_diode_sampling_controller:diode1": {"dim": 0},
        },
    }
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


def test_consecutive_scans__ascan_ascan(local_flint):
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


def test_plot_with_new_roi(local_flint):
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
