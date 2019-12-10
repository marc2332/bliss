# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from datetime import datetime
from nexus_writer_service.utils import data_policy


def test_data_policy_names():
    assert data_policy.valid_proposal_name("  XY_ 00  ") == "xy00"
    assert data_policy.valid_beamline_name("__ID - 00 ") == "id00"
    with pytest.raises(ValueError):
        data_policy.valid_proposal_name("00xy")
    with pytest.raises(ValueError):
        data_policy.valid_beamline_name("00id")


def test_data_policy_newexperiment(session):
    scan_saving = session.scan_saving

    data_policy.newexperiment()
    bl = scan_saving.beamline
    monthsubdir = datetime.now().strftime("%y%b").lower()
    proposal = datetime.now().strftime("{}%y%m".format(bl))
    assert scan_saving.base_path == "/data/{}/inhouse/{}".format(bl, monthsubdir)
    assert scan_saving.experiment == proposal

    data_policy.newexperiment("BLC-123")
    assert scan_saving.base_path == "/data/{}/inhouse/{}".format(bl, monthsubdir)
    assert scan_saving.experiment == "blc123"

    data_policy.newexperiment("HG-123")
    assert scan_saving.base_path == "/data/visitor"
    assert scan_saving.experiment == "hg123"


def test_data_policy_newtmpexperiment(session):
    scan_saving = session.scan_saving

    data_policy.newtmpexperiment()
    bl = scan_saving.beamline
    assert scan_saving.base_path == "/data/{}/tmp".format(bl)
    assert len(scan_saving.experiment) == 6

    data_policy.newtmpexperiment(root="/a/b")
    assert scan_saving.base_path == "/a/b"
    assert len(scan_saving.experiment) == 6

    data_policy.newtmpexperiment("XY-00")
    assert scan_saving.base_path == "/data/{}/tmp".format(bl)
    assert scan_saving.experiment == "xy00"

    data_policy.newtmpexperiment("XY-00", root="/a/b")
    assert scan_saving.base_path == "/a/b"
    assert scan_saving.experiment == "xy00"
