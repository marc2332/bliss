"""Testing manager module."""

from bliss.flint.manager.manager import ManageMainBehaviours
from bliss.flint.model import flint_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.helper import scan_info_helper


def _create_ascan_scan_info(master_name, extra_name=None):
    result = {
        "type": "ascan",
        "acquisition_chain": {
            "axis": {
                "master": {"scalars": [master_name]},
                "scalars": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "simulation_diode_sampling_controller:diode1",
                    "simulation_diode_sampling_controller:diode2",
                ],
            }
        },
    }
    if extra_name is not None:
        result["acquisition_chain"]["axis"]["scalars"].append(extra_name)
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
        "acquisition_chain": {
            "timer": {
                "master": {"scalars": ["timer:elapsed_time", "timer:epoch"]},
                "scalars": ["simulation_diode_sampling_controller:diode1"],
            }
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
