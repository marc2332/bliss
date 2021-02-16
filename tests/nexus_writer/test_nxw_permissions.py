# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import pytest
from bliss.common import scans
from nexus_writer_service.utils.scan_utils import scan_filename
from nexus_writer_service.io.io_utils import mkdir
from nexus_writer_service.io import nexus
from tests.nexus_writer.helpers import nxw_test_utils
from ..utils.os_utils import enable_write_permissions, disable_write_permissions


def test_nxw_permissions(nexus_writer_config):
    _test_nxw_permissions(**nexus_writer_config)


def test_nxw_permissions_alt(nexus_writer_config_alt):
    _test_nxw_permissions(**nexus_writer_config_alt)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_permissions(session=None, **kwargs):
    if session.scan_saving.writer == "nexus":
        _test_tango(session=session, **kwargs)
    else:
        _test_process(session=session, **kwargs)


def _test_tango(session=None, tmpdir=None, writer=None, **kwargs):
    detector = session.env_dict["diode3"]

    # File directory is a file itself (scan should not start)
    datasetdir = session.scan_saving.get_path()
    sampledir = os.path.dirname(datasetdir)
    mkdir(sampledir)
    with open(datasetdir, mode="w") as f:
        f.write("test")
    with pytest.raises(RuntimeError):
        scans.sct(0.1, detector, save=True)
    os.remove(datasetdir)
    mkdir(datasetdir)

    # File directory does not have write permissions (scan should not start)
    with disable_write_permissions(datasetdir) as disabled:
        if disabled:
            with pytest.raises(RuntimeError):
                scans.sct(0.1, detector, save=True)

    # File already exists with wrong permission
    scan = scans.sct(0.1, detector, save=True)
    nxw_test_utils.wait_scan_data_exists([scan], writer=writer)
    filename = scan_filename(scan)
    with disable_write_permissions(filename) as disabled:
        if disabled:
            with pytest.raises(RuntimeError):
                scans.sct(0.1, detector, save=True)

    # We should have permissions (scan should run)
    with enable_write_permissions(filename):
        scan = scans.sct(0.1, detector, save=True)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)


def _test_process(session=None, tmpdir=None, writer=None, **kwargs):
    detector = session.env_dict["diode3"]

    # File already exists with wrong permission
    scan = scans.sct(0.1, detector, save=True)
    filename = scan_filename(scan)
    with disable_write_permissions(filename) as disabled:
        if disabled:
            with pytest.raises(RuntimeError):
                scans.sct(0.1, detector, save=True)

    # We should have permissions (scan should run)
    with enable_write_permissions(filename):
        scan = scans.sct(0.1, detector, save=True)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
