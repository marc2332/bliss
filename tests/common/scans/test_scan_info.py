# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Test for backward compatibility created for BLISS 1.7.

Can be removed in few version together with ScanInfoFactory.
"""
from bliss.common.scans.scan_info import ScanInfoFactory


def test_1_set_request():
    scan_info = {}
    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta(
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
    assert "channels" in scan_info
    assert "foo" in scan_info["channels"]
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
    assert scan_info["channels"]["foo"] == expected


def test_2_set_request():
    scan_info = {}
    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta("foo", group="a")
    factory.set_channel_meta("bar", group="b")
    assert len(scan_info["channels"]) == 2


def test_add_scatter_plot():
    scan_info = {}
    factory = ScanInfoFactory(scan_info)
    factory.add_scatter_plot(x="a", y="b", value="c")
    assert "plots" in scan_info
    expected = {
        "kind": "scatter-plot",
        "items": [{"kind": "scatter", "x": "a", "y": "b", "value": "c"}],
    }
    assert scan_info["plots"] == [expected]


def test_add_2_scatter_plots():
    scan_info = {}
    factory = ScanInfoFactory(scan_info)
    factory.add_scatter_plot(x="a", y="b", value="c")
    factory.add_scatter_plot(name="foo", x="a2", y="b2", value="c2")
    assert "plots" in scan_info
    assert len(scan_info["plots"]) == 2


def test_add_scatter_axis():
    """It is valid to specify only part of the scatter item"""
    scan_info = {}
    factory = ScanInfoFactory(scan_info)
    factory.add_scatter_plot(x="a", y="b")
    expected = {"kind": "scatter", "x": "a", "y": "b"}
    assert scan_info["plots"][0]["items"] == [expected]
