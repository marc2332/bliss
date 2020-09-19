# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import pytest
from gevent.time import time
from bliss.common import scans
from bliss.scanning.scan import ScanAbort
from bliss.data.node import get_session_node
from tests.nexus_writer.helpers import nxw_test_utils
from tests.nexus_writer.helpers import nxw_test_data


def test_nxw_timescan(nexus_writer_config):
    _test_nxw_timescan(**nexus_writer_config)


# VDS of MCA raises exception when npoints not equal
# so scan writer is in FAULT state.
@pytest.mark.skip("skip until timescan has same npoints for each scan")
def test_nxw_timescan_alt(nexus_writer_config_alt):
    _test_nxw_timescan(**nexus_writer_config_alt)


def test_nxw_timescan_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_timescan(**nexus_writer_config_nopolicy)


def test_nxw_timescan_base(nexus_writer_base):
    _test_nxw_timescan(**nexus_writer_base)


@pytest.mark.skip("skip until timescan has same npoints for each scan")
def test_nxw_timescan_base_alt(nexus_writer_base_alt):
    _test_nxw_timescan(**nexus_writer_base_alt)


def test_nxw_timescan_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_timescan(**nexus_writer_base_nopolicy)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_timescan(session=None, tmpdir=None, writer=None, **kwargs):
    nodes = {}
    started = gevent.event.Event()
    nminevents = 5

    def listenscan(scannode):
        print(f"Listen to scan {scannode.db_name}")
        for event_type, node, event_data in scannode.walk_events():
            if event_type == event_type.NEW_DATA:
                name = node.fullname
                if not name:
                    continue
                if name in nodes:
                    nodes[name] += 1
                else:
                    nodes[name] = 1
                    started.set()

    def listensession():
        sessionnode = get_session_node(session.name)
        listeners = []
        try:
            for event_type, node, event_data in sessionnode.walk_events(filter="scan"):
                if event_type == event_type.NEW_NODE:
                    listeners.append(gevent.spawn(listenscan, node))
        finally:
            for g in listeners:
                g.kill()

    glisten = gevent.spawn(listensession)
    scan = scans.timescan(.1, run=False)
    gscan = nxw_test_utils.run_scan(scan, runasync=True)

    with gevent.Timeout(30):
        # Wait until first channel has data
        print("Wait for the first NEW_DATA event ...")
        started.wait()
        # Wait until all channels have nmin data events
        while any(v <= nminevents for v in nodes.values()):
            lst = set(nodes.values())
            nmin = min(lst)
            nmax = max(lst)
            print(
                f"Wait until all channels have at least {nminevents} data events (currently {nmin}/{nmax}) ..."
            )
            gevent.sleep(1)
            try:
                gscan.get(block=False)
            except gevent.Timeout:
                continue
        print(f"All channels have at least {nminevents} data events.")

    # Stop scan and listener
    print("Stopping scan ...")
    with gevent.Timeout(30):
        with pytest.raises(ScanAbort):
            print("Sending CTRL-C ...")
            gscan.kill(KeyboardInterrupt)
            print("Wait for scan to stop ...")
            gscan.get()
        print("Stopping listener ...")
        glisten.kill()

    # Verify data
    print("Verify data ...")
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_data(
        scan, scan_shape=(0,), positioners=[["elapsed_time", "epoch"]], **kwargs
    )
