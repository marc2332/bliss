"""Testing scan info helper module."""

from bliss.flint.helper import scan_info_helper
from bliss.flint.model import scan_model
from bliss.flint.model import plot_item_model


SCAN_INFO = {
    "acquisition_chain": {
        "timer": {
            "display_names": {"diode:diode": "diode", "images": []},
            "master": {
                "display_names": {
                    "timer:elapsed_time": "elapsed_time",
                    "timer:epoch": "epoch",
                },
                "images": [],
                "scalars": ["timer:elapsed_time", "timer:epoch"],
                "scalars_units": {"timer:elapsed_time": "s", "timer:epoch": "s"},
                "spectra": [],
            },
            "scalars": ["diode:diode"],
            "scalars_units": {"diode:diode": None, "spectra": []},
        },
        "timer2": {"spectra": ["opium:mca1"], "images": ["lima:image1"]},
    }
}


def test_iter_channels():
    result = scan_info_helper.iter_channels(SCAN_INFO)
    expected = [
        scan_info_helper.Channel("diode:diode", "scalar", "diode", "timer"),
        scan_info_helper.Channel("timer:elapsed_time", "scalar", "timer", "timer"),
        scan_info_helper.Channel("timer:epoch", "scalar", "timer", "timer"),
        scan_info_helper.Channel("opium:mca1", "spectrum", "opium", "timer2"),
        scan_info_helper.Channel("lima:image1", "image", "lima", "timer2"),
    ]
    assert set(result) == set(expected)


def test_create_scan_model():
    scan = scan_info_helper.create_scan_model(SCAN_INFO)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 5
    assert deviceCount == 5

    expected = [
        ("diode:diode", scan_model.ChannelType.COUNTER, "diode", "timer"),
        ("timer:elapsed_time", scan_model.ChannelType.COUNTER, "timer", "timer"),
        ("timer:epoch", scan_model.ChannelType.COUNTER, "timer", "timer"),
        ("opium:mca1", scan_model.ChannelType.SPECTRUM, "opium", "timer2"),
        ("lima:image1", scan_model.ChannelType.IMAGE, "lima", "timer2"),
    ]

    for channel_info in expected:
        name, kind, device, master = channel_info
        channel = scan.getChannelByName(name)
        assert channel.name() == name
        assert channel.type() == kind
        assert channel.device().name() == device
        if device == master:
            assert channel.device().master() is None
        else:
            assert channel.device().master().name() == master


def test_create_plot_model():
    # FIXME: Replace it with something stronger
    plots = scan_info_helper.create_plot_model(SCAN_INFO)
    assert len(plots) >= 0


def test_create_scatter_plot_model():
    scan_info = {
        "data_dim": 2,
        "acquisition_chain": {
            "axis": {
                "master": {
                    "scalars": ["axis:roby", "axis:robz"],
                    "scalars_units": {"axis:roby": None, "axis:robz": "mm"},
                    "spectra": [],
                    "images": [],
                    "display_names": {"axis:roby": "roby", "axis:robz": "robz"},
                },
                "scalars": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "simulation_diode_controller:diode",
                    "simulation_diode_controller:diode2",
                    "simulation_diode_controller:diode3",
                    "axis:roby",
                    "axis:robz",
                    "axis:roby",
                    "axis:robz",
                ],
                "scalars_units": {
                    "timer:elapsed_time": "s",
                    "timer:epoch": "s",
                    "simulation_diode_controller:diode": None,
                    "simulation_diode_controller:diode2": None,
                    "simulation_diode_controller:diode3": None,
                },
                "spectra": [],
                "images": [],
                "display_names": {
                    "timer:elapsed_time": "elapsed_time",
                    "timer:epoch": "epoch",
                    "simulation_diode_controller:diode": "diode",
                    "simulation_diode_controller:diode2": "diode2",
                    "simulation_diode_controller:diode3": "diode3",
                },
            }
        },
        "npoints2": 6,
        "npoints1": 6,
    }
    result_plots = scan_info_helper.create_plot_model(scan_info)
    plots = [
        plot for plot in result_plots if isinstance(plot, plot_item_model.ScatterPlot)
    ]
    assert len(plots) == 1
    plot = plots[0]
    assert len(plot.items()) == 1
    item = plot.items()[0]
    assert type(item) == plot_item_model.ScatterItem
    assert item.xChannel().name() == "axis:roby"
    assert item.yChannel().name() == "axis:robz"
    assert item.valueChannel().name() == "simulation_diode_controller:diode"

    plots = [
        plot for plot in result_plots if isinstance(plot, plot_item_model.CurvePlot)
    ]
    assert len(plots) == 1
    plot = plots[0]
    assert len(plot.items()) >= 1
    item = plot.items()[0]
    assert type(item) == plot_item_model.CurveItem
    # The first channel should be the diode/time
    assert item.xChannel().name() == "timer:elapsed_time"
    assert item.yChannel().name() == "simulation_diode_controller:diode"


def test_create_curve_plot_from_motor_scan():

    scan_info = {
        "acquisition_chain": {
            "axis": {
                "master": {
                    "scalars": ["axis:roby"],
                    "scalars_units": {"axis:roby": None},
                    "spectra": [],
                    "images": [],
                    "display_names": {"axis:roby": "roby"},
                },
                "scalars": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "simulation_diode_controller:diode",
                    "simulation_diode_controller:diode2",
                ],
                "scalars_units": {
                    "timer:elapsed_time": "s",
                    "timer:epoch": "s",
                    "simulation_diode_controller:diode": None,
                    "simulation_diode_controller:diode2": None,
                },
                "spectra": [],
                "images": [],
                "display_names": {
                    "timer:elapsed_time": "elapsed_time",
                    "timer:epoch": "epoch",
                    "simulation_diode_controller:diode": "diode",
                    "simulation_diode_controller:diode2": "diode2",
                },
            }
        }
    }

    result_plots = scan_info_helper.create_plot_model(scan_info)
    plots = [
        plot for plot in result_plots if isinstance(plot, plot_item_model.CurvePlot)
    ]
    assert len(plots) == 1
    plot = plots[0]
    curves = []
    for item in plot.items():
        curves.append((item.xChannel().name(), item.yChannel().name()))
    expected_curves = [
        ("axis:roby", "simulation_diode_controller:diode"),
        ("axis:roby", "simulation_diode_controller:diode2"),
    ]
    assert set(expected_curves) == set(curves)
