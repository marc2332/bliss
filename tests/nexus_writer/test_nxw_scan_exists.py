# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common import scans
from louie import dispatcher
import nxw_test_utils
from nexus_writer_service.io import nexus


def test_nxw_scan_exists(nexus_writer_config):
    _test_nxw_scan_exists(**nexus_writer_config)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_scan_exists(session=None, tmpdir=None, writer=None, **kwargs):
    detectors = session.env_dict["diode3"], session.env_dict["diode4"]
    scan = scans.ct(.1, *detectors, save=True)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    with nexus.nxRoot(session.scan_saving.filename, mode="a") as root:
        nexus.nxEntry(root, "2.1")
        with pytest.raises(nexus.NexusInstanceExists):
            nexus.nxEntry(root, "2.1", raise_on_exists=True)
    with pytest.raises(RuntimeError):
        scan = scans.ct(.1, *detectors, save=True)
    scan = scans.ct(.1, *detectors, save=True)
    # TODO: no proper cleanup by Bliss
    dispatcher.reset()
