# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common import scans


def test_nxw_nowriter(alias_session):
    alias_session.scan_saving.writer = "nexus"
    det = alias_session.env_dict["lima_simulator"]
    with pytest.raises(RuntimeError):
        scans.ct(0.1, det, save=True)
