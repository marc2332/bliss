# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import pytest
import nxw_test_utils
from bliss.common import scans
from nexus_writer_service.utils.scan_utils import scan_filename, scan_uri
from nexus_writer_service.io.io_utils import mkdir
from nexus_writer_service.io import nexus


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


def disable_permissions(path):
    if os.geteuid():
        os.chmod(path, 0o544)
        return True
    else:
        status = os.system("chattr +i " + path)
        return os.WEXITSTATUS(status) == 0


def enable_permissions(path):
    if os.geteuid():
        os.chmod(path, 0o755)
        return True
    else:
        status = os.system("chattr -i " + path)
        return os.WEXITSTATUS(status) == 0


def _test_tango(session=None, tmpdir=None, writer=None, **kwargs):
    detector = session.env_dict["diode3"]

    # File directory is a file itself (scan should not start)
    datasetdir = session.scan_saving.get_path()
    sampledir = os.path.dirname(datasetdir)
    mkdir(sampledir)
    with open(datasetdir, mode="w") as f:
        f.write("test")
    with pytest.raises(RuntimeError):
        scans.ct(0.1, detector, save=True)
    os.remove(datasetdir)
    mkdir(datasetdir)

    # File directory does not have write permissions (scan should not start)
    if disable_permissions(datasetdir):
        with pytest.raises(RuntimeError):
            scans.ct(0.1, detector, save=True)
        enable_permissions(datasetdir)

    # File already exists with wrong permission
    scan = scans.ct(0.1, detector, save=True)
    filename = scan_filename(scan)
    if disable_permissions(filename):
        with pytest.raises(RuntimeError):
            scans.ct(0.1, detector, save=True)

        # We should have permissions (scan should run)
        enable_permissions(filename)
        scan = scans.ct(0.1, detector, save=True)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)


def _test_process(session=None, tmpdir=None, writer=None, **kwargs):
    detector = session.env_dict["diode3"]

    # File already exists with wrong permission
    scan = scans.ct(0.1, detector, save=True)
    filename = scan_filename(scan)
    if disable_permissions(filename):
        scan = scans.ct(0.1, detector, save=True)
        uri = scan_uri(scan)
        assert not nexus.exists(uri), uri

        # We should have permissions (scan should run)
        enable_permissions(filename)
        scan = scans.ct(0.1, detector, save=True)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
