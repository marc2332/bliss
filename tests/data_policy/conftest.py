# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import os


@pytest.fixture
def esrf_data_policy(session, scan_tmpdir):
    session.enable_esrf_data_policy()
    scan_saving_config = session.scan_saving.scan_saving_config
    # patch config to put data to the proper test directory
    scan_saving_config["inhouse_data_root"] = os.path.join(
        scan_tmpdir, "{beamline}", "inhouse"
    )
    scan_saving_config["tmp_data_root"] = os.path.join(scan_tmpdir, "{beamline}", "tmp")
    scan_saving_config["visitor_data_root"] = os.path.join(scan_tmpdir, "visitor")
    yield scan_saving_config
    session.disable_esrf_data_policy()
