# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_tango_shutter(beacon, dummy_tango_server):
    sh = beacon.get("safshut")

    assert repr(sh).startswith("safshut")
    assert sh.name == "safshut"
    assert sh.config["name"] == "safshut"

    sh.open()
    assert sh.state == 0
    assert sh.state_string[1] == sh.STATE2STR[0][1]

    sh.close()
    assert sh.state == 1
    assert sh.state_string[1] == sh.STATE2STR[1][1]

    sh.open()
    assert sh.state == 0
    assert sh.state_string[1] == sh.STATE2STR[0][1]

    assert isinstance(sh.state_string, tuple)
