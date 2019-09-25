# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.controllers.tango_shutter import TangoShutterState


def test_tango_shutter(beacon, dummy_tango_server):
    sh = beacon.get("safshut")

    assert repr(sh).startswith("safshut")
    assert sh.name == "safshut"
    assert sh.config["name"] == "safshut"

    sh.open(timeout=3)
    assert sh.state == TangoShutterState.OPEN
    assert sh.state_string[0] == TangoShutterState.OPEN.value

    sh.close(timeout=3)
    assert sh.state == TangoShutterState.CLOSED
    assert sh.state_string[0] == TangoShutterState.CLOSED.value

    assert isinstance(sh.state_string, tuple)
