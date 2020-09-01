"""Testing manager module."""

from bliss.flint.manager.manager import ManageMainBehaviours
from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.helper import scan_info_helper


def test_updated_model(local_flint):
    """
    Test plot state with consecutive scans

    Create a loopscan -> elapsed_time should be the axis
    Then create a ascan -> the motor should be the axis
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

    ascan_info = {
        "type": "ascan",
        "acquisition_chain": {
            "axis": {
                "master": {"scalars": ["axis:sx"]},
                "scalars": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "simulation_diode_sampling_controller:diode1",
                    "simulation_diode_sampling_controller:diode2",
                ],
            }
        },
    }
    scan = scan_info_helper.create_scan_model(ascan_info)
    plots = scan_info_helper.create_plot_model(ascan_info, scan)
    manager.updateScanAndPlots(scan, plots)

    model = widget.plotModel()
    item = model.items()[0]
    assert item.xChannel().name() == "axis:sx"
