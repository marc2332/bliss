# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import os
from bliss.common import scans
from nexus_writer_service.utils import scan_utils


def test_nxw_receiving_events(nexus_writer_base_withoutpolicy):
    session, scan_tmpdir, writer_stdout = nexus_writer_base_withoutpolicy
    scan = scans.loopscan(10, .1)
    # as we don't have any synchronisation for now
    gevent.sleep(3)
    with gevent.Timeout(1, RuntimeError("no answer from NexusWriter")):
        out = writer_stdout.read1()
    # Session listener received event?
    assert b"NEW_NODE received for scan" in out
    # Expected files being created?
    # scan_utils.open_scan_data(scan)
    for filename in scan_utils.filenames():
        assert os.path.isfile(filename), filename
