# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import nxw_test_utils
import nxw_test_data


def test_nxw_notes(nexus_writer_config):
    _test_nxw_notes(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_notes(session=None, tmpdir=None, writer=None, **kwargs):
    scan = scans.ct(.1, run=False, save=True)
    notes = ["test1", "text2", "text3"]
    for note in notes:
        scan.add_comment(note)
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_data(scan, notes=notes, **kwargs)
