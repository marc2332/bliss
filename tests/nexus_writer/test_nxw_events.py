# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import nxw_test_utils


def test_nxw_events(nexus_writer_config):
    _test_nxw_events(**nexus_writer_config, config=True)


def test_nxw_events_base(nexus_writer_base):
    _test_nxw_events(**nexus_writer_base, config=False)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_events(session=None, tmpdir=None, writer=None, **kwargs):
    scan = scans.loopscan(1, .1)
    nxw_test_utils.wait_scan_data_exists([scan], writer=writer, **kwargs)
