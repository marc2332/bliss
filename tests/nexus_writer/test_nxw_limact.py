
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import nxw_test_utils
import nxw_test_data


def test_nxw_limact(nexus_writer_config):
    _test_nxw_limact(**nexus_writer_config)


def test_nxw_limact_alt(nexus_writer_config_alt):
    _test_nxw_limact(**nexus_writer_config_alt)


def test_nxw_limact_nopolicy(nexus_writer_config_nopolicy):
    _test_nxw_limact(**nexus_writer_config_nopolicy)


def test_nxw_limact_base(nexus_writer_base):
    _test_nxw_limact(**nexus_writer_base)


def test_nxw_limact_base_alt(nexus_writer_base_alt):
    _test_nxw_limact(**nexus_writer_base_alt)


def test_nxw_limact_base_nopolicy(nexus_writer_base_nopolicy):
    _test_nxw_limact(**nexus_writer_base_nopolicy)


def _test_nxw_limact(session=None, tmpdir=None, writer=None, **kwargs):
    lima = session.env_dict["lima_simulator"]
    scan = session.env_dict["limact"](lima, 0.1)
    nxw_test_utils.run_scan(scan)
    nxw_test_utils.wait_scan_data_finished([scan], writer=writer)
    if kwargs["config"]:
        detectors = ["^lima_simulator$"]
    else:
        detectors = ["^lima_simulator_image$"]
    nxw_test_data.assert_scan_data(
        scan,
        scan_shape=(1,),
        positioners=[[]],
        detectors=detectors,
        hastimer=False,
        **kwargs
    )
