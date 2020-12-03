# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.scanning.scan_info import ScanInfo


def test_1_set_request():
    scan_info = ScanInfo()
    scan_info.set_channel_meta(
        "foo",
        start=1,
        stop=2,
        min=3,
        max=4,
        points=5,
        axis_points=6,
        axis_id=1,
        axis_kind="forth",
        group="g",
    )
    assert "requests" in scan_info
    assert "foo" in scan_info["requests"]
    expected = {
        "start": 1,
        "stop": 2,
        "min": 3,
        "max": 4,
        "points": 5,
        "axis-points": 6,
        "axis-id": 1,
        "axis-kind": "forth",
        "group": "g",
    }
    assert scan_info["requests"]["foo"] == expected


def test_2_set_request():
    scan_info = ScanInfo()
    scan_info.set_channel_meta("foo", group="a")
    scan_info.set_channel_meta("bar", group="b")
    assert len(scan_info["requests"]) == 2


def test_add_scatter_plot():
    scan_info = ScanInfo()
    scan_info.add_scatter_plot(x="a", y="b", value="c")
    assert "plots" in scan_info
    expected = {
        "kind": "scatter-plot",
        "items": [{"kind": "scatter", "x": "a", "y": "b", "value": "c"}],
    }
    assert scan_info["plots"] == [expected]


def test_add_2_scatter_plots():
    scan_info = ScanInfo()
    scan_info.add_scatter_plot(x="a", y="b", value="c")
    scan_info.add_scatter_plot(name="foo", x="a2", y="b2", value="c2")
    assert "plots" in scan_info
    assert len(scan_info["plots"]) == 2


def test_add_scatter_axis():
    """It is valid to specify only part of the scatter item"""
    scan_info = ScanInfo()
    scan_info.add_scatter_plot(x="a", y="b")
    expected = {"kind": "scatter", "x": "a", "y": "b"}
    assert scan_info["plots"][0]["items"] == [expected]
