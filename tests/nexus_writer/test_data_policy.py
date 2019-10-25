# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os
from datetime import datetime
from nexus_writer_service.utils import data_policy


def test_data_policy_names():
    assert data_policy.valid_proposal_name("  XY_ 00  ") == "xy00"
    assert data_policy.valid_beamline_name("__ID - 00 ") == "id00"
    with pytest.raises(ValueError):
        data_policy.valid_proposal_name("00xy")
    with pytest.raises(ValueError):
        data_policy.valid_beamline_name("00id")


def test_data_policy_basepath(session):
    scan_saving = session.scan_saving  # env_dict["SCAN_SAVING"]

    data_policy.newvisitor("XY-00")
    assert scan_saving.base_path == "/data/visitor"
    assert scan_saving.experiment == "xy00"

    with pytest.raises(ValueError):
        data_policy.newvisitor(None)

    data_policy.newinhouse("XY-00")
    bl = scan_saving.beamline
    now = datetime.now().strftime("%y%b").lower()
    assert scan_saving.base_path == "/data/{}/inhouse/{}".format(bl, now)
    assert scan_saving.experiment == "xy00"

    data_policy.newinhouse(None)
    proposal = datetime.now().strftime("{}%y%m".format(bl))
    assert scan_saving.base_path == "/data/{}/inhouse/default".format(bl)
    assert scan_saving.experiment == proposal

    data_policy.newdefaultexperiment()
    assert scan_saving.base_path == "/data/{}/inhouse/default".format(bl)
    assert scan_saving.experiment == proposal

    data_policy.newtmpexperiment("XY-00")
    assert up(scan_saving.base_path) == "/data/{}/tmp".format(bl)
    assert scan_saving.experiment == "xy00"

    data_policy.newtmpexperiment()
    assert up(scan_saving.base_path) == "/data/{}/tmp".format(bl)
    assert len(scan_saving.experiment) == 6

    data_policy.newlocalexperiment("XY-00", root="/a/b")
    assert scan_saving.base_path == "/a/b"
    assert scan_saving.experiment == "xy00"

    data_policy.newlocalexperiment("XY-00")
    assert up(scan_saving.base_path) == "/tmp"
    assert scan_saving.experiment == "xy00"

    data_policy.newlocalexperiment(root="/a/b")
    assert scan_saving.base_path == "/a/b"
    assert len(scan_saving.experiment) == 6

    data_policy.newlocalexperiment()
    assert up(scan_saving.base_path) == "/tmp"
    assert len(scan_saving.experiment) == 6


def up(path):
    return os.path.normpath(os.path.join(path, ".."))
