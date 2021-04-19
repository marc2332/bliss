"""Testing manager module."""

from bliss.flint.manager.manager import ManageMainBehaviours
from bliss.flint.model import flint_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.helper import scan_info_helper


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
