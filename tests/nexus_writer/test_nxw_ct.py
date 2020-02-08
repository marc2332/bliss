# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import nxw_test_utils
import nxw_test_data


def test_nxw_ct(nexus_writer_config):
    _test_nxw_ct(**nexus_writer_config)


def test_nxw_ct_alt(nexus_writer_config_alt):
    _test_nxw_ct(**nexus_writer_config_alt)


def test_nxw_ct_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_ct(**nexus_writer_config_nopolicy)


def test_nxw_ct_base(nexus_writer_base):
    _test_nxw_ct(**nexus_writer_base)


def test_nxw_ct_base_alt(nexus_writer_base_alt):
    _test_nxw_ct(**nexus_writer_base_alt)


def test_nxw_ct_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_ct(**nexus_writer_base_nopolicy)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_ct(session=None, tmpdir=None, writer=None, **kwargs):
    scan = scans.ct(.1, run=False, save=True)
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    nxw_test_data.assert_scan_data(scan, **kwargs)
