# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss import setup_globals
from bliss.common import scans
from bliss.scanning.chain import AcquisitionChain, AcquisitionMaster, AcquisitionSlave
from bliss.scanning.scan import Scan

from tests.conftest import deep_compare


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
        s.scan_info["acquisition_chain"]["timer"]["scalars_units"][
            "simulation_diode_sampling_controller:diode"
        ]
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


def test_scan_meta_master_and_device(session, scan_meta):
    scan_meta.clear()
    master_dict = {"super master": 10}

    class DummyMaster(AcquisitionMaster):
        name = "my_master"

        def __init__(self):
            super().__init__(name="my_master")

        def fill_meta_at_scan_start(self, scan_meta):
            scan_meta.instrument.set(self, master_dict)

        def prepare(self):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    device_name = "my_slave"
    device_dict = {
        "lima": {
            device_name: {
                "threshold": 12000,
                "rois counter": {"roi1": (0, 10, 100, 200)},
            }
        }
    }

    class DummyDevice(AcquisitionSlave):
        name = device_name

        def __init__(self):
            super().__init__(name=device_name)

        def fill_meta_at_scan_start(self, scan_meta):
            scan_meta.instrument.set(self, device_dict)

        def prepare(self):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    master = DummyMaster()
    slave = DummyDevice()
    chain = AcquisitionChain()
    chain.add(master, slave)

    s = Scan(chain, name="my_simple")
    s.run()
    assert s.scan_info["instrument"] == {**master_dict, **device_dict}


def test_positioners_in_scan_info(alias_session):
    env_dict = alias_session.env_dict
    lima_simulator = env_dict["lima_simulator"]
    robyy = env_dict["robyy"]
    diode = alias_session.config.get("diode")

    # test that positioners are remaining in for a simple counter that does not update 'scan_info'
    s1 = scans.ascan(robyy, 0, 1, 3, .1, diode, run=False, save=False)

    robyy.rmove(0.1)  # related to issue #1179
    initial_robyy_position = robyy.position

    s1.run()
    assert "positioners" in s1.scan_info
    assert (
        s1.scan_info["positioners"]["positioners_start"]["robyy"]
        == initial_robyy_position
    )
    assert "positioners_dial_start" in s1.scan_info["positioners"]
    assert "positioners_end" in s1.scan_info["positioners"]
    assert "positioners_dial_end" in s1.scan_info["positioners"]
    assert "positioners_units" in s1.scan_info["positioners"]

    # test that positioners are remaining in for a counter that updates 'scan_info'
    initial_robyy_position = robyy.position
    s2 = scans.ascan(robyy, 0, 1, 3, .1, lima_simulator, run=False, save=False)
    s2.run()
    assert "positioners" in s2.scan_info
    assert (
        s2.scan_info["positioners"]["positioners_start"]["robyy"]
        == initial_robyy_position
    )


def test_scan_saving_without_axis_in_session(default_session):
    # put scan file in a tmp directory
    diode = default_session.config.get("diode")

    s = scans.loopscan(3, .1, diode, save=False)

    assert "positioners" in s.scan_info
    assert s.scan_info["positioners"]["positioners_start"] == {}


def test_scan_info_object_vs_node(session):
    transf = session.config.get("transfocator_simulator")  # noqa: F841
    roby = session.env_dict["roby"]
    diode = session.env_dict["diode"]

    s1 = scans.ascan(roby, 0, 1, 3, .1, diode, save=False)

    deep_compare(s1.scan_info, s1.node.info.get_all())


def test_scan_comment_feature(default_session):
    diode = default_session.config.get("diode")

    def f():
        s = scans.loopscan(10, .1, diode, run=False, save=False)
        s.add_comment("comment1")
        g = gevent.spawn(s.run)
        s.add_comment("comment2")
        gevent.sleep(.2)
        s.add_comment("comment3")
        g.get()
        return s

    s = f()
    assert len(s.scan_info["comments"]) == 3
    assert len(s.node.info["comments"]) == 3

    with pytest.raises(RuntimeError):
        s.add_comment("comment4")
