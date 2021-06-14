"""Testing scan info helper module."""

import numpy
from bliss.flint.helper import scan_info_helper
from bliss.flint.model import scan_model
from bliss.flint.model import plot_item_model
from tests.qt.flint.factory import ScanInfoFactory


SCAN_INFO_POSITIONERS = {
    "positioners": {
        "positioners_start": {"slit_bottom": 1.0, "slit_top": -1.0},
        "positioners_end": {"slit_bottom": 2.0, "slit_top": -2.0},
        "positioners_dial_start": {"slit_bottom": 3.0, "slit_top": -3.0},
        "positioners_dial_end": {"slit_bottom": 4.0},
        "positioners_units": {"slit_bottom": "mm", "slit_top": None, "slit_foo": None},
    }
}


def test_iter_channels():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_device(root_id="timer2", device_id="timer2")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)
    factory.add_device(root_id="timer", device_id="diode", triggered_by="timer")
    factory.add_device(root_id="timer2", device_id="opium", triggered_by="timer2")
    factory.add_device(root_id="timer2", device_id="lima", triggered_by="timer2")
    factory.add_channel(channel_id="diode:diode", dim=0)
    factory.add_channel(channel_id="opium:mca1", dim=1)
    factory.add_channel(channel_id="lima:image1", dim=2)
    scan_info = factory.scan_info()

    result = scan_info_helper.iter_channels(scan_info)
    result = [
        scan_info_helper.ChannelInfo(r.name, None, r.device, r.master) for r in result
    ]
    expected = [
        scan_info_helper.ChannelInfo("diode:diode", None, "diode", "timer"),
        scan_info_helper.ChannelInfo("timer:elapsed_time", None, "timer", "timer"),
        scan_info_helper.ChannelInfo("timer:epoch", None, "timer", "timer"),
        scan_info_helper.ChannelInfo("opium:mca1", None, "opium", "timer2"),
        scan_info_helper.ChannelInfo("lima:image1", None, "lima", "timer2"),
    ]
    assert set(result) == set(expected)


def test_create_scan_model():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_device(root_id="timer2", device_id="timer2")
    meta = {"points": 10}
    factory.add_channel(
        device_id="timer", channel_id="timer:elapsed_time", dim=0, meta=meta
    )
    factory.add_channel(channel_id="timer:epoch", dim=0)
    factory.add_device(root_id="timer", device_id="diode", triggered_by="timer")
    factory.add_device(root_id="timer2", device_id="opium", triggered_by="timer2")
    factory.add_device(root_id="timer2", device_id="lima", triggered_by="timer2")
    factory.add_channel(channel_id="diode:diode", dim=0)
    factory.add_channel(channel_id="opium:mca1", dim=1)
    factory.add_channel(channel_id="lima:image1", dim=2)
    scan_info = factory.scan_info()

    scan = scan_info_helper.create_scan_model(scan_info)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 5
    assert deviceCount == 7

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

    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)

    factory.add_channel(channel_id="timer:epoch", dim=0)
    rois = {
        "roi1": {"kind": "rect", "x": 190, "y": 110, "width": 600, "height": 230},
        "roi4": {
            "kind": "arc",
            "cx": 487.0,
            "cy": 513.0,
            "r1": 137.0,
            "r2": 198.0,
            "a1": -172.0,
            "a2": -300.0,
        },
    }

    factory.add_lima_device(
        device_id="beamviewer",
        root_id="timer",
        triggered_by="timer",
        image=True,
        rois=rois,
    )
    factory.add_channel(channel_id="beamviewer:roi_counters:roi1_sum", dim=0)
    factory.add_channel(channel_id="beamviewer:roi_counters:roi1_avg", dim=0)
    factory.add_channel(channel_id="beamviewer:roi_counters:roi4_sum", dim=0)
    factory.add_channel(channel_id="beamviewer:roi_counters:roi4_avg", dim=0)
    factory.add_channel(channel_id="beamviewer:roi_counters:roi5_avg", dim=0)
    scan_info = factory.scan_info()
    scan = scan_info_helper.create_scan_model(scan_info)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 8
    assert deviceCount == 6

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
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_device(root_id="timer2", device_id="timer2")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)
    factory.add_device(root_id="timer", device_id="diode", triggered_by="timer")
    factory.add_device(root_id="timer2", device_id="opium", triggered_by="timer2")
    factory.add_device(root_id="timer2", device_id="lima", triggered_by="timer2")
    factory.add_channel(channel_id="diode:diode", dim=0)
    factory.add_channel(channel_id="opium:mca1", dim=1)
    factory.add_channel(channel_id="lima:image1", dim=2)
    scan_info = factory.scan_info()

    plots = scan_info_helper.create_plot_model(scan_info)
    # default curve plot + image plot + onedim plot
    assert len(plots) == 3


def test_create_scatter_plot_model():
    factory = ScanInfoFactory()
    factory["data_dim"] = 2
    factory.add_device(root_id="axis", device_id="axis")
    factory.add_device(root_id="axis", device_id="timer", triggered_by="axis")
    factory.add_device(root_id="axis", device_id="diode", triggered_by="axis")
    factory.add_channel(channel_id="axis:roby", dim=0)
    factory.add_channel(channel_id="axis:robz", dim=0)
    factory.add_channel(channel_id="timer:elapsed_time", unit="s")
    factory.add_channel(channel_id="diode:diode", dim=0)
    factory.add_channel(channel_id="diode:diode2", dim=0)
    factory.add_channel(channel_id="diode:diode3", dim=0)
    scan_info = factory.scan_info()

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
    assert item.valueChannel().name() == "diode:diode"

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
    assert item.yChannel().name() == "diode:diode"


def test_create_curve_plot_from_motor_scan():
    factory = ScanInfoFactory()
    factory.add_device(root_id="axis", device_id="axis")
    factory.add_device(root_id="axis", device_id="timer", triggered_by="axis")
    factory.add_device(root_id="axis", device_id="diode", triggered_by="axis")
    factory.add_channel(channel_id="axis:roby", dim=0)
    factory.add_channel(channel_id="timer:elapsed_time", dim=0, unit="s")
    factory.add_channel(channel_id="diode:diode", dim=0)
    factory.add_channel(channel_id="diode:diode2", dim=0)
    scan_info = factory.scan_info()

    result_plots = scan_info_helper.create_plot_model(scan_info)
    plots = [
        plot for plot in result_plots if isinstance(plot, plot_item_model.CurvePlot)
    ]
    assert len(plots) == 1
    plot = plots[0]
    curves = []
    for item in plot.items():
        curves.append((item.xChannel().name(), item.yChannel().name()))
    expected_curves = [("axis:roby", "diode:diode")]
    assert set(expected_curves) == set(curves)


def test_amesh_scan_with_image_and_mca():
    factory = ScanInfoFactory()
    factory["data_dim"] = 2
    factory.add_device(root_id="axis", device_id="axis")
    factory.add_device(root_id="axis", device_id="timer", triggered_by="axis")
    factory.add_device(root_id="axis", device_id="diode", triggered_by="axis")
    factory.add_device(
        root_id="axis", device_id="mca1", triggered_by="axis", type="mca"
    )
    factory.add_lima_device(
        root_id="axis", device_id="tomocam", image=True, triggered_by="axis"
    )
    factory.add_channel(channel_id="axis:sy", dim=0)
    factory.add_channel(channel_id="axis:sz", dim=0)
    factory.add_channel(channel_id="timer:elapsed_time", unit="s")
    factory.add_channel(channel_id="timer:epoch", unit="s")
    factory.add_channel(channel_id="diode:diode", dim=0)
    factory.add_channel(channel_id="mca1:realtime_det0", dim=0)
    factory.add_channel(channel_id="mca1:spectrum_det0", dim=1)
    factory["plots"] = [
        {
            "kind": "scatter-plot",
            "items": [{"kind": "scatter", "x": "axis:sy", "y": "axis:sz"}],
        },
        {
            "kind": "scatter-plot",
            "name": "foo",
            "items": [{"kind": "scatter", "x": "axis:sy", "y": "axis:sz"}],
        },
    ]
    scan_info = factory.scan_info()
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


def test_create_plot_model_with_rois():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)

    factory.add_channel(channel_id="timer:epoch", dim=0)
    rois = {
        "roi1": {"kind": "rect", "x": 190, "y": 110, "width": 600, "height": 230},
        "roi4": {
            "kind": "arc",
            "cx": 487.0,
            "cy": 513.0,
            "r1": 137.0,
            "r2": 198.0,
            "a1": -172.0,
            "a2": -300.0,
        },
    }

    factory.add_lima_device(
        device_id="beamviewer",
        root_id="timer",
        triggered_by="timer",
        image=True,
        rois=rois,
    )
    scan_info = factory.scan_info()

    scan = scan_info_helper.create_scan_model(scan_info)
    plots = scan_info_helper.infer_plot_models(scan)
    image_plots = [p for p in plots if isinstance(p, plot_item_model.ImagePlot)]
    plot = image_plots[0]
    roi_items = [i for i in plot.items() if isinstance(i, plot_item_model.RoiItem)]
    assert len(roi_items) == 2
    for item in roi_items:
        roi = item.roi(scan)
        assert roi is not None


def test_progress_percent_curve():
    scan_info = {
        "npoints": 10,
        "acquisition_chain": {"main": {"devices": ["main"]}},
        "devices": {"main": {"channels": ["axis:roby"]}},
        "channels": {"axis:roby": {"dim": 0}},
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
        "acquisition_chain": {"main": {"devices": ["main"]}},
        "devices": {"main": {"channels": ["axis:roby"]}},
        "channels": {"axis:roby": {"dim": 0}},
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
        "acquisition_chain": {"main": {"devices": ["main"]}},
        "devices": {"main": {"channels": ["axis:roby"]}},
        "channels": {"axis:roby": {"dim": 2}},
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
        1, 2, 3, 4, 5, 1, 6, scan_model.AxisKind.FORTH, None, None, None
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
        "dim": 3,
    }
    result = scan_info_helper.parse_channel_metadata(meta)
    expected = scan_model.ChannelMetadata(
        1, 2, 3, 4, 5, 0, 6, scan_model.AxisKind.BACKNFORTH, None, None, 3
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
    expected = scan_model.ChannelMetadata(
        1, 2, 3, None, 5, None, 6, None, None, None, None
    )
    assert result == expected


def test_get_all_positioners():
    positioners = scan_info_helper.get_all_positioners(SCAN_INFO_POSITIONERS)
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


def test_read_plot_models__curve_axis():
    scan_info = {
        "plots": [
            {
                "name": "plot",
                "kind": "scatter-plot",
                "items": [{"kind": "scatter", "x": "a"}],
            }
        ]
    }
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 1
    assert len(plots[0].items()) == 1
    item = plots[0].items()[0]
    assert item.xChannel().name() == "a"
    assert item.yChannel() is None


def test_read_plot_models__curve_item():
    scan_info = {
        "plots": [
            {
                "name": "plot",
                "kind": "curve-plot",
                "items": [{"kind": "curve", "x": "a", "y": "b"}],
            }
        ]
    }
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 1
    assert len(plots[0].items()) == 1
    item = plots[0].items()[0]
    assert item.xChannel().name() == "a"
    assert item.yChannel().name() == "b"
    assert item.yAxis() == "left"


def test_read_plot_models__curve_right_item():
    scan_info = {
        "plots": [
            {
                "name": "plot",
                "kind": "curve-plot",
                "items": [{"kind": "curve", "x": "a", "y": "b", "y_axis": "right"}],
            }
        ]
    }
    plots = scan_info_helper.read_plot_models(scan_info)
    assert len(plots) == 1
    assert len(plots[0].items()) == 1
    item = plots[0].items()[0]
    assert item.xChannel().name() == "a"
    assert item.yChannel().name() == "b"
    assert item.yAxis() == "right"


def test_read_scatter_data__different_groups():
    scan_info = {
        "acquisition_chain": {"timer": {"devices": ["timer"]}},
        "devices": {"timer": {"channels": ["foo", "foo2", "bar"]}},
        "channels": {
            "foo": {"group": "scatter1", "axis-id": 0},
            "foo2": {"group": "scatter1", "axis-id": 1},
            "bar": {"group": "scatter2", "axis-id": 0},
        },
    }
    scan = scan_info_helper.create_scan_model(scan_info)
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
        "acquisition_chain": {"timer": {"devices": ["timer"]}},
        "devices": {"timer": {"channels": ["foo", "foo2", "bar"]}},
        "channels": {
            "foo": {"group": "scatter1", "axis-id": 0},
            "foo2": {"group": "scatter1", "axis-id": 0},
            "bar": {"group": "scatter1", "axis-id": 1},
        },
    }
    scan = scan_info_helper.create_scan_model(scan_info)
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
        "acquisition_chain": {"timer": {"devices": ["timer"]}},
        "devices": {"timer": {"channels": ["axis1", "axis2", "diode1", "frame"]}},
        "channels": {
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
        },
    }

    scan = scan_info_helper.create_scan_model(scan_info)
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


def test_read_onedim_detector():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)
    factory.add_device(root_id="timer", device_id="onedim", triggered_by="timer")
    factory.add_channel(channel_id="onedim:d1", dim=1)
    factory.add_channel(channel_id="onedim:d2", dim=1)
    scan_info = factory.scan_info()

    scan = scan_info_helper.create_scan_model(scan_info)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    assert len(plots) == 1
    plot = plots[0]
    assert isinstance(plot, plot_item_model.OneDimDataPlot)
    assert len(plot.items()) == 2
    item = plot.items()[0]
    assert isinstance(item, plot_item_model.XIndexCurveItem)


def test_read_onedim_detector__xaxis_array():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)
    onedim_meta = {"xaxis_array": numpy.array([0, 1, 4])}
    factory.add_device(
        root_id="timer", device_id="onedim", triggered_by="timer", meta=onedim_meta
    )
    factory.add_channel(channel_id="onedim:d1", dim=1)
    factory.add_channel(channel_id="onedim:d2", dim=1)
    scan_info = factory.scan_info()

    scan = scan_info_helper.create_scan_model(scan_info)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    assert len(plots) == 1
    plot = plots[0]
    assert isinstance(plot, plot_item_model.OneDimDataPlot)
    assert len(plot.items()) == 2
    item = plot.items()[0]
    assert isinstance(item, plot_item_model.CurveItem)
    numpy.testing.assert_array_equal(item.xData(scan).array(), [0, 1, 4])


def test_read_onedim_detector__xaxis_channel():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)
    onedim_meta = {"xaxis_channel": "onedim:d1"}
    factory.add_device(
        root_id="timer", device_id="onedim", triggered_by="timer", meta=onedim_meta
    )
    factory.add_channel(channel_id="onedim:d1", dim=1)
    factory.add_channel(channel_id="onedim:d2", dim=1)
    scan_info = factory.scan_info()

    scan = scan_info_helper.create_scan_model(scan_info)
    plots = scan_info_helper.create_plot_model(scan_info, scan)
    assert len(plots) == 1
    plot = plots[0]
    assert isinstance(plot, plot_item_model.OneDimDataPlot)
    assert len(plot.items()) == 1
    item = plot.items()[0]
    assert isinstance(item, plot_item_model.CurveItem)
    assert item.xChannel().name() == "onedim:d1"
    assert item.yChannel().name() == "onedim:d2"


def test_create_scan_model_with_mca():
    factory = ScanInfoFactory()
    factory.add_device(root_id="timer", device_id="timer")
    factory.add_channel(channel_id="timer:elapsed_time", dim=0)
    factory.add_channel(channel_id="timer:epoch", dim=0)
    factory.add_device(
        root_id="timer", device_id="mca", triggered_by="timer", type="mca"
    )
    factory.add_channel(channel_id="mca:realtime_det0", dim=0)
    factory.add_channel(channel_id="mca:realtime_det1", dim=0)
    factory.add_channel(channel_id="mca:deadtime_det0", dim=0)
    factory.add_channel(channel_id="mca:deadtime_det1", dim=0)
    scan_info = factory.scan_info()

    scan = scan_info_helper.create_scan_model(scan_info)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 6
    assert deviceCount == 5

    channel = scan.getChannelByName("mca:realtime_det0")
    assert channel.name() == "mca:realtime_det0"
    device = channel.device()
    assert device.name() == "det0"
    assert device.type() == scan_model.DeviceType.VIRTUAL_MCA_DETECTOR
