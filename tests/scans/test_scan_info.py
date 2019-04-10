# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss import setup_globals
from bliss.common import scans


def test_scan_info_scalars_units(session):
    heater = getattr(setup_globals, "heater")
    diode = getattr(setup_globals, "diode")
    roby = getattr(setup_globals, "roby")
    robz = getattr(setup_globals, "robz")
    s = scans.loopscan(1, .1, heater, diode, run=False)
    assert (
        s.scan_info["acquisition_chain"]["timer"]["scalars_units"]["heater:heater"]
        == "deg"
    )
    assert (
        s.scan_info["acquisition_chain"]["timer"]["scalars_units"]["diode:diode"]
        is None
    )
    s2 = scans.ascan(robz, 0, 1, 3, .1, heater, run=False)
    assert (
        s2.scan_info["acquisition_chain"]["axis"]["master"]["scalars_units"][
            "axis:robz"
        ]
        == "mm"
    )
    s3 = scans.ascan(roby, 0, 1, 3, .1, heater, run=False)
    assert (
        s3.scan_info["acquisition_chain"]["axis"]["master"]["scalars_units"][
            "axis:roby"
        ]
        is None
    )


def test_scan_info_display_names(session):
    heater = getattr(setup_globals, "heater")
    roby = getattr(setup_globals, "roby")
    s = scans.ascan(roby, 0, 1, 3, .1, heater, run=False)
    assert (
        s.scan_info["acquisition_chain"]["axis"]["master"]["display_names"]["axis:roby"]
        == "roby"
    )
    assert (
        s.scan_info["acquisition_chain"]["axis"]["display_names"]["heater:heater"]
        == "heater"
    )


def test_scan_meta_function(scan_meta):
    scan_meta.clear()
    info_dict = {"name": "gold", "bla": 10, "truc": "super mario"}

    def f(scan):
        return info_dict

    scan_meta.sample.set("my_func", f)
    scan_meta_dict = scan_meta.to_dict(None)
    assert scan_meta_dict["sample"] == info_dict


def test_scan_meta_order_function(scan_meta):
    scan_meta.clear()
    first_info = {"name": "gold", "bla": 10, "truc": "super mario"}
    scan_meta.sample.set("direct", first_info)
    second_dict = {"name": "silver"}

    def f(scan):
        return second_dict

    scan_meta.sample.set("func", f)
    scan_meta_dict = scan_meta.to_dict(None)
    final = first_info
    final.update(second_dict)
    assert scan_meta_dict["sample"] == final
    scan_meta.sample.remove("func")
    scan_meta_dict = scan_meta.to_dict(None)
    assert scan_meta_dict["sample"] == first_info
