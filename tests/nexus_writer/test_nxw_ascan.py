# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common import scans
import nxw_test_utils
import nxw_test_data


def test_nxw_ascan(nexus_writer_config):
    _test_nxw_ascan(*nexus_writer_config, config=True, withpolicy=True, alt=False)


def test_nxw_ascan_alt(nexus_writer_config_alt):
    _test_nxw_ascan(*nexus_writer_config_alt, config=True, withpolicy=True, alt=True)


def test_nxw_ascan_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_ascan(
        *nexus_writer_config_nopolicy, config=True, withpolicy=False, alt=False
    )


def test_nxw_ascan_base(nexus_writer_base):
    _test_nxw_ascan(*nexus_writer_base, config=False, withpolicy=True, alt=False)


def test_nxw_ascan_base_alt(nexus_writer_base_alt):
    _test_nxw_ascan(*nexus_writer_base_alt, config=False, withpolicy=True, alt=True)


def test_nxw_ascan_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_ascan(
        *nexus_writer_base_nopolicy, config=False, withpolicy=False, alt=False
    )


def _test_nxw_ascan(
    session, scan_tmpdir, writer_stdout, config=True, withpolicy=True, alt=False
):
    masters = ("robx",)
    scan_shape = (10,)
    scan = scans.ascan(
        session.env_dict[masters[0]], 0, 1, scan_shape[0] - 1, .1, run=False
    )
    nxw_test_utils.run_scan(scan)
    # As we don't have any synchronisation for now:
    nxw_test_utils.wait_scan_data_finished(
        [scan], config=config, writer_stdout=writer_stdout
    )
    nxw_test_data.assert_scan_data(
        scan,
        masters=masters,
        scan_shape=scan_shape,
        config=config,
        withpolicy=withpolicy,
        alt=alt,
        writer_stdout=writer_stdout,
    )
