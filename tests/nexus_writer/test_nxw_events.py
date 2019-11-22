# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
from bliss.common import scans
import nxw_test_utils


def test_nxw_events(nexus_writer_config):
    _test_nxw_events(*nexus_writer_config, config=True)


def test_nxw_events_base(nexus_writer_base):
    _test_nxw_events(*nexus_writer_base, config=False)


def _test_nxw_events(session, scan_tmpdir, writer_stdout, config=True):
    scan = scans.loopscan(1, .1)
    # As we don't have any synchronisation for now:
    nxw_test_utils.wait_scan_data_exists([scan], config=config)
    # Session listener received event?
    with gevent.Timeout(1, RuntimeError("no answer from NexusWriter")):
        out = writer_stdout.read1()
    try:
        assert b"NEW_NODE event received for scan" in out
        # Expected files being created?
        nxw_test_utils.assert_scan_data_exists(scan, config=config)
    except Exception:
        for line in out.split(b"\n"):
            print(line.decode())
        raise
