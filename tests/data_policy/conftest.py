# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os


def replace_mount_points(scan_saving_config, test_root, key):
    """Replace /tmp/scans with the test directory root
    """
    mount_points = scan_saving_config[key]
    if isinstance(mount_points, str):
        scan_saving_config[key] = mount_points.replace("/tmp/scans", test_root)
    else:
        for k in mount_points:
            mount_points[k] = mount_points[k].replace("/tmp/scans", test_root)


@pytest.fixture
def esrf_data_policy(session, scan_tmpdir):
    session.enable_esrf_data_policy()
    scan_saving_config = session.scan_saving.scan_saving_config
    test_root = str(scan_tmpdir)
    keys = [
        "tmp_data_root",
        "icat_tmp_data_root",
        "visitor_data_root",
        "inhouse_data_root",
    ]
    for key in keys:
        replace_mount_points(scan_saving_config, test_root, key)
    yield scan_saving_config
    session.disable_esrf_data_policy()
