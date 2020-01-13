"""Testing scan info helper module."""

import numpy
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
    },
    "requests": {"timer:elapsed_time": {"points": 10}},
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
    assert deviceCount == 6

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
        assert channel.device().master().name() == master

    assert scan.getChannelByName("timer:elapsed_time").metadata() is not None
    assert scan.getChannelByName("timer:epoch").metadata() is None


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
                    "simulation_diode_sampling_controller:diode",
                    "simulation_diode_sampling_controller:diode2",
                    "simulation_diode_sampling_controller:diode3",
                    "axis:roby",
                    "axis:robz",
                    "axis:roby",
                    "axis:robz",
                ],
                "scalars_units": {
                    "timer:elapsed_time": "s",
                    "timer:epoch": "s",
                    "simulation_diode_sampling_controller:diode": None,
                    "simulation_diode_sampling_controller:diode2": None,
                    "simulation_diode_sampling_controller:diode3": None,
                },
                "spectra": [],
                "images": [],
                "display_names": {
                    "timer:elapsed_time": "elapsed_time",
                    "timer:epoch": "epoch",
                    "simulation_diode_sampling_controller:diode": "diode",
                    "simulation_diode_sampling_controller:diode2": "diode2",
                    "simulation_diode_sampling_controller:diode3": "diode3",
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
    assert item.valueChannel().name() == "simulation_diode_sampling_controller:diode"

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
    assert item.yChannel().name() == "simulation_diode_sampling_controller:diode"


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
                    "simulation_diode_sampling_controller:diode",
                    "simulation_diode_sampling_controller:diode2",
                ],
                "scalars_units": {
                    "timer:elapsed_time": "s",
                    "timer:epoch": "s",
                    "simulation_diode_sampling_controller:diode": None,
                    "simulation_diode_sampling_controller:diode2": None,
                },
                "spectra": [],
                "images": [],
                "display_names": {
                    "timer:elapsed_time": "elapsed_time",
                    "timer:epoch": "epoch",
                    "simulation_diode_sampling_controller:diode": "diode",
                    "simulation_diode_sampling_controller:diode2": "diode2",
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
        ("axis:roby", "simulation_diode_sampling_controller:diode"),
        ("axis:roby", "simulation_diode_sampling_controller:diode2"),
    ]
    assert set(expected_curves) == set(curves)


def test_progress_percent_curve():
    scan_info = {
        "npoints": 10,
        "acquisition_chain": {"axis": {"master": {"scalars": ["axis:roby"]}}},
    }
    scan = scan_info_helper.create_scan_model(scan_info)
    channel = scan.getChannelByName("axis:roby")
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 0.0

    data = scan_model.Data(scan, numpy.arange(5))
    channel.setData(data)
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 0.5

    data = scan_model.Data(scan, numpy.arange(10))
    channel.setData(data)
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 1.0


def test_progress_percent_scatter():
    scan_info = {
        "npoints1": 2,
        "npoints2": 5,
        "acquisition_chain": {"axis": {"master": {"scalars": ["axis:roby"]}}},
    }
    scan = scan_info_helper.create_scan_model(scan_info)
    channel = scan.getChannelByName("axis:roby")
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 0.0

    data = scan_model.Data(scan, numpy.arange(5))
    channel.setData(data)
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 0.5

    data = scan_model.Data(scan, numpy.arange(10))
    channel.setData(data)
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 1.0


def test_progress_percent_image():
    scan_info = {
        "npoints": 10,
        "acquisition_chain": {"axis": {"master": {"images": ["axis:roby"]}}},
    }
    scan = scan_info_helper.create_scan_model(scan_info)
    channel = scan.getChannelByName("axis:roby")
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 0.0

    image = numpy.arange(4).reshape(2, 2)
    data = scan_model.Data(scan, image, frameId=0)
    channel.setData(data)
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 0.1

    data = scan_model.Data(scan, image, frameId=9)
    channel.setData(data)
    res = scan_info_helper.get_scan_progress_percent(scan)
    assert res == 1.0


def test_parse_channel_metadata():
    meta = {
        "start": 1,
        "stop": 2,
        "min": 3,
        "max": 4,
        "points": 5,
        "axes-points": 6,
        "axes-kind": "slow",
    }
    result = scan_info_helper.parse_channel_metadata(meta)
    assert result == scan_model.ChannelMetadata(
        1, 2, 3, 4, 5, 6, scan_model.AxesKind.SLOW
    )


def test_parse_wrong_values():
    meta = {
        "start": 1,
        "stop": 2,
        "min": 3,
        "max": "foo",
        "points": 5,
        "axes-points": 6,
        "axes-kind": "foo",
        "foo": "bar",
    }
    result = scan_info_helper.parse_channel_metadata(meta)
    assert result == scan_model.ChannelMetadata(1, 2, 3, None, 5, 6, None)
