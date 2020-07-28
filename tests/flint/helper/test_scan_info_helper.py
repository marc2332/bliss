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
    "positioners": {
        "positioners_start": {"slit_bottom": 1.0, "slit_top": -1.0},
        "positioners_end": {"slit_bottom": 2.0, "slit_top": -2.0},
        "positioners_dial_start": {"slit_bottom": 3.0, "slit_top": -3.0},
        "positioners_dial_end": {"slit_bottom": 4.0},
        "positioners_units": {"slit_bottom": "mm", "slit_top": None, "slit_foo": None},
    },
}


SCAN_INFO_LIMA_ROIS = {
    "acquisition_chain": {
        "timer": {
            "master": {"scalars": ["timer:elapsed_time", "timer:epoch"]},
            "scalars": [
                "beamviewer:roi_counters:roi1_sum",
                "beamviewer:roi_counters:roi1_avg",
                "beamviewer:roi_counters:roi4_sum",
                "beamviewer:roi_counters:roi4_avg",
            ],
        }
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


def test_create_scan_model_with_lima_rois():
    scan = scan_info_helper.create_scan_model(SCAN_INFO_LIMA_ROIS)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 6
    assert deviceCount == 6

    channel = scan.getChannelByName("beamviewer:roi_counters:roi4_avg")
    assert channel.name() == "beamviewer:roi_counters:roi4_avg"
    assert channel.device().name() == "roi4"
    assert channel.device().type() == scan_model.DeviceType.VIRTUAL_ROI


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
    expected_curves = [("axis:roby", "simulation_diode_sampling_controller:diode")]
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


def test_parse_channel_metadata__bliss_1_4():
    meta = {
        "start": 1,
        "stop": 2,
        "min": 3,
        "max": 4,
        "points": 5,
        "axis-points": 6,
        "axis-kind": "slow",
    }
    result = scan_info_helper.parse_channel_metadata(meta)
    expected = scan_model.ChannelMetadata(
        1, 2, 3, 4, 5, 1, 6, scan_model.AxisKind.FORTH, None, None
    )
    assert result == expected


def test_parse_channel_metadata():
    meta = {
        "start": 1,
        "stop": 2,
        "min": 3,
        "max": 4,
        "points": 5,
        "axis-id": 0,
        "axis-points": 6,
        "axis-kind": "backnforth",
    }
    result = scan_info_helper.parse_channel_metadata(meta)
    expected = scan_model.ChannelMetadata(
        1, 2, 3, 4, 5, 0, 6, scan_model.AxisKind.BACKNFORTH, None, None
    )
    assert result == expected


def test_parse_wrong_values():
    meta = {
        "start": 1,
        "stop": 2,
        "min": 3,
        "max": "foo",
        "points": 5,
        "axis-points": 6,
        "axis-kind": "foo",
        "foo": "bar",
    }
    result = scan_info_helper.parse_channel_metadata(meta)
    expected = scan_model.ChannelMetadata(1, 2, 3, None, 5, None, 6, None, None, None)
    assert result == expected


def test_get_all_positioners():
    positioners = scan_info_helper.get_all_positioners(SCAN_INFO)
    assert len(positioners) == 3
    assert positioners[0] == scan_info_helper.PositionerDescription(
        "slit_bottom", 1, 2, 3, 4, "mm"
    )
    assert positioners[1] == scan_info_helper.PositionerDescription(
        "slit_top", -1, -2, -3, None, None
    )
    assert positioners[2] == scan_info_helper.PositionerDescription(
        "slit_foo", None, None, None, None, None
    )


def test_read_plot_models__empty_scatter():
    scan_info = {"plots": [{"name": "plot", "kind": "scatter-plot"}]}
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 1


def test_read_plot_models__empty_scatters():
    scan_info = {
        "plots": [
            {"name": "plot", "kind": "scatter-plot"},
            {"name": "plot", "kind": "scatter-plot"},
        ]
    }
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 2


def test_read_plot_models__scatter():
    scan_info = {
        "plots": [
            {
                "name": "plot",
                "kind": "scatter-plot",
                "items": [{"kind": "scatter", "x": "a", "y": "b", "value": "c"}],
            }
        ]
    }
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 1
    assert len(plots[0].items()) == 1
    item = plots[0].items()[0]
    assert item.xChannel().name() == "a"
    assert item.yChannel().name() == "b"
    assert item.valueChannel().name() == "c"


def test_read_plot_models__scatter_axis():
    scan_info = {
        "plots": [
            {
                "name": "plot",
                "kind": "scatter-plot",
                "items": [{"kind": "scatter", "x": "a", "y": "b"}],
            }
        ]
    }
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 1
    assert len(plots[0].items()) == 1
    item = plots[0].items()[0]
    assert item.xChannel().name() == "a"
    assert item.yChannel().name() == "b"
    assert item.valueChannel() is None
