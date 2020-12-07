"""Testing scan info helper module."""

import numpy
from bliss.flint.helper import scan_info_helper
from bliss.flint.model import scan_model
from bliss.flint.model import plot_item_model


SCAN_INFO = {
    "acquisition_chain": {
        "timer": {
            "master": {
                "images": [],
                "scalars": ["timer:elapsed_time", "timer:epoch"],
                "spectra": [],
            },
            "scalars": ["diode:diode"],
        },
        "timer2": {"spectra": ["opium:mca1"], "images": ["lima:image1"]},
    },
    "channels": {
        "diode:diode": {"display_name": "diode"},
        "timer:elapsed_time": {"display_name": "elapsed_time", "unit": "s"},
        "timer:epoch": {"display_name": "epoch", "unit": "s"},
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
                "beamviewer:roi_counters:roi5_avg",
            ],
        }
    },
    "rois": {
        "beamviewer:roi_counters:roi1": {
            "kind": "rect",
            "x": 190,
            "y": 110,
            "width": 600,
            "height": 230,
        },
        "beamviewer:roi_counters:roi4": {
            "kind": "arc",
            "cx": 487.0,
            "cy": 513.0,
            "r1": 137.0,
            "r2": 198.0,
            "a1": -172.0,
            "a2": -300.0,
        },
    },
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

    assert scan.getChannelByName("timer:elapsed_time").metadata().points is not None
    assert scan.getChannelByName("timer:epoch").metadata().points is None


def test_create_scan_model_with_lima_rois():
    scan = scan_info_helper.create_scan_model(SCAN_INFO_LIMA_ROIS)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 7
    assert deviceCount == 7

    channel = scan.getChannelByName("beamviewer:roi_counters:roi1_avg")
    device = channel.device()
    assert device.metadata().roi is not None
    assert device.metadata().roi.x == 190

    channel = scan.getChannelByName("beamviewer:roi_counters:roi4_avg")
    assert channel.name() == "beamviewer:roi_counters:roi4_avg"
    device = channel.device()
    assert device.name() == "roi4"
    assert device.type() == scan_model.DeviceType.VIRTUAL_ROI
    assert device.metadata().roi is not None
    assert device.metadata().roi.cx == 487.0

    channel = scan.getChannelByName("beamviewer:roi_counters:roi5_avg")
    device = channel.device()
    assert device.metadata().roi is None


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
                    "spectra": [],
                    "images": [],
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
                "spectra": [],
                "images": [],
            }
        },
        "channels": {
            "axis:roby": {"display_name": "roby"},
            "axis:robz": {"display_name": "robz", "unit": "mm"},
            "timer:elapsed_time": {"display_name": "elapsed_time", "unit": "s"},
            "timer:epoch": {"display_name": "epoch", "unit": "s"},
            "simulation_diode_sampling_controller:diode": {"display_name": "diode"},
            "simulation_diode_sampling_controller:diode2": {"display_name": "diode2"},
            "simulation_diode_sampling_controller:diode3": {"display_name": "diode3"},
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
                "master": {"scalars": ["axis:roby"], "spectra": [], "images": []},
                "scalars": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "simulation_diode_sampling_controller:diode",
                    "simulation_diode_sampling_controller:diode2",
                ],
                "spectra": [],
                "images": [],
            }
        },
        "channels": {
            "axis:roby": {"display_name": "roby"},
            "axis:robz": {"display_name": "robz", "unit": "mm"},
            "timer:elapsed_time": {"display_name": "elapsed_time", "unit": "s"},
            "timer:epoch": {"display_name": "epoch", "unit": "s"},
            "simulation_diode_sampling_controller:diode": {"display_name": "diode"},
            "simulation_diode_sampling_controller:diode2": {"display_name": "diode2"},
        },
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


def test_amesh_scan_with_image_and_mca():

    scan_info = {
        "type": "amesh",
        "title": "amesh sy -0.75 0.75 30 sz -0.75 0.75 30 0.001",
        "data_dim": 2,
        "npoints": 961,
        "start": [-0.75, -0.75],
        "stop": [0.75, 0.75],
        "count_time": 0.001,
        "npoints1": 31,
        "npoints2": 31,
        "requests": {
            "axis:sy": {
                "start": -0.75,
                "stop": 0.75,
                "points": 961,
                "axis-points": 31,
                "axis-id": 0,
                "axis-kind": "forth",
                "group": "scatter",
            },
            "axis:sz": {
                "start": -0.75,
                "stop": 0.75,
                "points": 961,
                "axis-points": 31,
                "axis-id": 1,
                "axis-kind": "forth",
                "group": "scatter",
            },
            "timer:elapsed_time": {"group": "scatter"},
            "timer:epoch": {"group": "scatter"},
            "SampleStageDiode:fluo_signal": {"group": "scatter"},
            "mca1:realtime_det0": {"group": "scatter"},
            "mca1:trigger_livetime_det0": {"group": "scatter"},
            "mca1:energy_livetime_det0": {"group": "scatter"},
            "mca1:triggers_det0": {"group": "scatter"},
            "mca1:events_det0": {"group": "scatter"},
            "mca1:icr_det0": {"group": "scatter"},
            "mca1:ocr_det0": {"group": "scatter"},
            "mca1:deadtime_det0": {"group": "scatter"},
        },
        "plots": [
            {
                "kind": "scatter-plot",
                "items": [{"kind": "scatter", "x": "axis:sy", "y": "axis:sz"}],
            },
            {
                "kind": "scatter-plot",
                "name": "foo",
                "items": [{"kind": "scatter", "x": "axis:sy", "y": "axis:sz"}],
            },
        ],
        "acquisition_chain": {
            "axis": {
                "master": {"scalars": ["axis:sy", "axis:sz"]},
                "scalars": [
                    "timer:elapsed_time",
                    "timer:epoch",
                    "SampleStageDiode:fluo_signal",
                    "mca1:realtime_det0",
                    "mca1:trigger_livetime_det0",
                    "mca1:energy_livetime_det0",
                    "mca1:triggers_det0",
                    "mca1:events_det0",
                    "mca1:icr_det0",
                    "mca1:ocr_det0",
                    "mca1:deadtime_det0",
                ],
                "spectra": ["mca1:spectrum_det0"],
                "images": ["tomocam:image"],
            }
        },
        "_display_extra": {"plotselect": []},
    }
    scan = scan_info_helper.create_scan_model(scan_info)
    result_plots = scan_info_helper.create_plot_model(scan_info, scan)
    result_kinds = [type(p) for p in result_plots]
    assert set(result_kinds) == set(
        [
            plot_item_model.ScatterPlot,
            plot_item_model.CurvePlot,
            plot_item_model.ImagePlot,
            plot_item_model.McaPlot,
        ]
    )
    # The first one is the scatter
    assert result_kinds[0] == plot_item_model.ScatterPlot
    assert result_kinds[1] == plot_item_model.ScatterPlot
    assert result_plots[1].name() == "foo"


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


def test_read_scatter_data__different_groups():
    scan_info = {
        "requests": {
            "foo": {"group": "scatter1", "axis-id": 0},
            "foo2": {"group": "scatter1", "axis-id": 1},
            "bar": {"group": "scatter2", "axis-id": 0},
        }
    }
    scan = scan_info_helper.create_scan_model(scan_info, False)
    foo = scan.getChannelByName("foo")
    scatterData = scan.getScatterDataByChannel(foo)
    assert scatterData is not None
    foo2 = scan.getChannelByName("foo2")
    assert scatterData.contains(foo2)
    bar = scan.getChannelByName("bar")
    assert not scatterData.contains(bar)
    assert scatterData.maxDim() == 2


def test_read_scatter_data__twice_axis_at_same_place():
    scan_info = {
        "requests": {
            "foo": {"group": "scatter1", "axis-id": 0},
            "foo2": {"group": "scatter1", "axis-id": 0},
            "bar": {"group": "scatter1", "axis-id": 1},
        }
    }
    scan = scan_info_helper.create_scan_model(scan_info, False)
    foo = scan.getChannelByName("foo")
    scatterData = scan.getScatterDataByChannel(foo)
    assert scatterData is not None
    foo2 = scan.getChannelByName("foo2")
    assert scatterData.contains(foo2)
    bar = scan.getChannelByName("bar")
    assert scatterData.contains(bar)
    assert scatterData.maxDim() == 2


def test_read_scatter_data__non_regular_3d():
    scan_info = {
        "requests": {
            "axis1": {
                "axis-id": 0,
                "axis-points-hint": 10,
                "group": "foo",
                "max": 9,
                "min": 0,
                "points": 500,
            },
            "axis2": {
                "axis-id": 1,
                "axis-points-hint": 10,
                "group": "foo",
                "max": 9,
                "min": 0,
                "points": 500,
            },
            "diode1": {"axis-points-hint": None, "group": "foo"},
            "frame": {
                "axis-id": 2,
                "axis-kind": "step",
                "axis-points": 5,
                "axis-points-hint": None,
                "group": "foo",
                "points": 500,
                "start": 0,
                "stop": 4,
            },
        }
    }

    scan = scan_info_helper.create_scan_model(scan_info, False)
    axis1 = scan.getChannelByName("axis1")
    scatterData = scan.getScatterDataByChannel(axis1)
    assert scatterData is not None
    axis2 = scan.getChannelByName("axis2")
    assert scatterData.contains(axis2)
    frame = scan.getChannelByName("frame")
    assert scatterData.contains(frame)
    diode1 = scan.getChannelByName("diode1")
    assert not scatterData.contains(diode1)
    assert scatterData.maxDim() == 3
