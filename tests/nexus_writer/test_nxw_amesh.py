# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import nxw_test_utils
import nxw_test_data


def test_nxw_amesh(nexus_writer_config):
    _test_nxw_amesh(**nexus_writer_config)


def test_nxw_amesh_alt(nexus_writer_config_alt):
    _test_nxw_amesh(**nexus_writer_config_alt, alt=True)


def test_nxw_amesh_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_amesh(**nexus_writer_config_nopolicy, withpolicy=False)


def test_nxw_amesh_base(nexus_writer_base):
    _test_nxw_amesh(**nexus_writer_base, config=False)


def test_nxw_amesh_base_alt(nexus_writer_base_alt):
    _test_nxw_amesh(**nexus_writer_base_alt, config=False, alt=True)


def test_nxw_amesh_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_amesh(**nexus_writer_base_nopolicy, config=False, withpolicy=False)


@nxw_test_utils.writer_stdout_on_exception
def _test_nxw_amesh(session=None, tmpdir=None, writer=None, **kwargs):
    masters = "robx", "roby"
    scan_shape = 4, 5
    scan = scans.amesh(
        session.env_dict[masters[0]],
        0,
        1,
        scan_shape[0] - 1,
        session.env_dict[masters[1]],
        0,
        1,
        scan_shape[1] - 1,
        .1,
        run=False,
    )
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer, **kwargs)
    nxw_test_data.assert_scan_data(
        scan, masters=masters, scan_shape=scan_shape, **kwargs
    )
