# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.counter import SamplingMode
from bliss.common.tango import DevSource
from bliss.common.scans import loopscan
from bliss.data.node import get_node


def test_machinfo_counters_issue1793(machinfo_tango_server, session):
    machinfo = session.config.get("machinfo")
    mg = session.config.get("issue1793_mg")
    for cnt in machinfo.counters:
        assert cnt.fullname in mg.available


def test_machinfo_conn_issue2333(machinfo_tango_server, session):
    machinfo = session.config.get("machinfo")
    p1 = machinfo.proxy
    assert p1 is machinfo.proxy  # check always the same proxy instance
    # check the counter controller is using the same instance
    assert (
        machinfo.counters.current._counter_controller._proxy is p1
    )  # check the counter controller is using the same instance
    assert all(cnt.mode == SamplingMode.SINGLE for cnt in machinfo.counters)
    assert machinfo.proxy.get_source() == DevSource.CACHE_DEV


def test_machinfo_in_scan(machinfo_tango_server, session):
    diode = session.config.get("diode")
    machinfo = session.config.get("machinfo")
    scan_with_current = loopscan(1, 0.1, diode, machinfo.counters.current)
    scan_without_current = loopscan(1, 0.1, diode)

    # Machine metadata should be always there, whether part of the scan or not
    assert "machine" in scan_with_current.scan_info["instrument"]
    assert "machine" in scan_without_current.scan_info["instrument"]
    assert "current" in scan_with_current.scan_info["instrument"]["machine"]
    assert "current" in scan_without_current.scan_info["instrument"]["machine"]

    # No Redis node for the machine when not part of the scan
    db_name = scan_without_current.node.db_name + ":timer:machinfo:current"
    node = get_node(db_name)
    assert node is None

    # Redis node exists when part of the scan but the node does not
    # contain the metadata for two reasons:
    # 1. the machinfo counter controller has not metadata
    #    -> a design flaw of MachInfo
    # 2. machinfo metadata is already in scan_info
    #    -> currently done to avoid double metadata gathering
    db_name = scan_with_current.node.db_name + ":timer:machinfo:current"
    node = get_node(db_name)
    assert node.info.get("current") is None
