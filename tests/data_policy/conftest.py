# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common.session import set_current_session
from bliss.scanning.scan_saving import ESRFScanSaving, ESRFDataPolicyEvent


def modify_esrf_policy_mount_points(scan_saving, base_path):
    # Make sure all data saving mount points
    # have base_path as root in the session's
    # scan saving config (in memory)
    assert isinstance(scan_saving, ESRFScanSaving)
    scan_saving_config = scan_saving.scan_saving_config
    roots = ["inhouse_data_root", "visitor_data_root", "tmp_data_root"]
    for root in roots:
        for prefix in ["", "icat_"]:
            key = prefix + root
            mount_points = scan_saving_config.get(key, None)
            if mount_points is None:
                continue
            elif isinstance(mount_points, str):
                scan_saving_config[key] = mount_points.replace("/tmp/scans", base_path)
            else:
                for mp in mount_points:
                    mount_points[mp] = mount_points[mp].replace("/tmp/scans", base_path)


def _esrf_data_policy(session):
    # SCAN_SAVING uses the `current_session`
    set_current_session(session, force=True)
    assert session.name == session.scan_saving.session

    # TODO: cannot use enable_esrf_data_policy directly because
    # we need to modify the in-memory config before setting the proposal.
    # If enable_esrf_data_policy changes however, we are in trouble.

    tmpdir = session.scan_saving.base_path
    session._set_scan_saving(cls=ESRFScanSaving)
    modify_esrf_policy_mount_points(session.scan_saving, tmpdir)

    # session.scan_saving.get_path() set the proposal to the default
    # proposal and notify ICAT. When using the `icat_subscriber` fixture,
    # this will be the first event.
    session._emit_event(
        ESRFDataPolicyEvent.Enable, data_path=session.scan_saving.get_path()
    )

    yield session.scan_saving.scan_saving_config

    session.disable_esrf_data_policy()


@pytest.fixture
def esrf_data_policy(session, icat_backend):
    yield from _esrf_data_policy(session)


@pytest.fixture
def esrf_data_policy_tango(session, icat_tango_backend):
    yield from _esrf_data_policy(session)


@pytest.fixture
def session2(beacon, scan_tmpdir):
    session = beacon.get("test_session2")
    session.setup()
    session.scan_saving.base_path = str(scan_tmpdir)
    yield session
    session.close()


@pytest.fixture
def esrf_data_policy2(session2, icat_backend):
    yield from _esrf_data_policy(session2)


@pytest.fixture
def esrf_data_policy2_tango(session2, icat_tango_backend):
    yield from _esrf_data_policy(session2)
