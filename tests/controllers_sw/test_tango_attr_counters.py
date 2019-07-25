# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_tac_undu(beacon, dummy_tango_server):
    tac_pos = beacon.get("tac_undu_position")

    u23a = beacon.get("u23a")

    assert u23a.position == 1.4
    assert u23a.position == tac_pos.read()
