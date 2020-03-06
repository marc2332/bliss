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
from bliss.data.node import get_session_node
import nxw_test_utils
import nxw_test_data


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
    t0 = None
    nminevents = 5
    tmax = 5

    def listenscan(scannode):
        nonlocal t0
        it = scannode.iterator
        for event_type, node, event_data in it.walk_events():
            if event_type == event_type.NEW_DATA:
                name = node.fullname
                if not name:
                    continue
                if name in nodes:
                    nodes[name] += 1
                else:
                    nodes[name] = 1
                    t0 = time()

    def listensession():
        it = get_session_node(session.name).iterator
        listeners = []
        try:
            for event_type, node, event_data in it.walk_events(filter="scan"):
                if event_type == event_type.NEW_NODE:
                    listeners.append(gevent.spawn(listenscan, node))
        finally:
            for g in listeners:
                g.kill()

    glisten = gevent.spawn(listensession)
    scan = scans.timescan(.1, run=False)
    gscan = nxw_test_utils.run_scan(scan, runasync=True)
    # Wait until first channel has data
    while t0 is None:
        gevent.sleep(0.1)
    # Wait until all channels have nmin data events
    while (time() - t0) < tmax or any(v <= nminevents for v in nodes.values()):
        gevent.sleep(1)
    # Stop scan and listener
    with pytest.raises(KeyboardInterrupt):
        gscan.kill(KeyboardInterrupt)
        gscan.join()
        gscan.get()
    glisten.kill()

    # Verify data
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_data(
        scan, scan_shape=(0,), positioners=[["elapsed_time", "epoch"]], **kwargs
    )
