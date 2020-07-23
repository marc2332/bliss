# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os


def _esrf_data_policy(session):
    tmpdir = session.scan_saving.base_path
    session.enable_esrf_data_policy()

    # Make sure all data saving mount points
    # have tmpdir as root
    scan_saving_config = session.scan_saving.scan_saving_config
    roots = ["inhouse_data_root", "visitor_data_root", "tmp_data_root"]
    for root in roots:
        for prefix in ["", "icat_"]:
            key = prefix + root
            mount_points = scan_saving_config.get(key, None)
            if mount_points is None:
                continue
            elif isinstance(mount_points, str):
                scan_saving_config[key] = mount_points.replace("/tmp/scans", tmpdir)
            else:
                for mp in mount_points:
                    mount_points[mp] = mount_points[mp].replace("/tmp/scans", tmpdir)

    yield scan_saving_config

    session.disable_esrf_data_policy()


@pytest.fixture
def esrf_data_policy(session):
    yield from _esrf_data_policy(session)


@pytest.fixture
def session2(beacon, scan_tmpdir):
    session = beacon.get("test_session2")
    session.setup()
    session.scan_saving.base_path = str(scan_tmpdir)
    yield session
    session.close()


@pytest.fixture
def esrf_data_policy2(session2):
    yield from _esrf_data_policy(session2)
