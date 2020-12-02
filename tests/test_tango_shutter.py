# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import logging
from bliss.controllers.tango_shutter import TangoShutterState


def test_tango_shutter(beacon, dummy_tango_server, caplog):
    sh = beacon.get("safshut")

    assert sh.name == "safshut"
    assert sh.config["name"] == "safshut"

    sh.open(timeout=3)
    assert sh.state == TangoShutterState.OPEN
    assert sh.state_string[0] == TangoShutterState.OPEN.value
    with caplog.at_level(logging.DEBUG, logger=f"global.controllers.{sh.name}"):
        sh.open()
        assert sh.state == TangoShutterState.OPEN
    assert "ignored" in caplog.messages[-1]

    sh.close(timeout=3)
    assert sh.state == TangoShutterState.CLOSED
    assert sh.state_string[0] == TangoShutterState.CLOSED.value
    with caplog.at_level(logging.DEBUG, logger=f"global.controllers.{sh.name}"):
        sh.close()
        assert sh.state == TangoShutterState.CLOSED
    assert "ignored" in caplog.messages[-1]

    assert isinstance(sh.state_string, tuple)

    sh.proxy.setDisabled(True)
    with caplog.at_level(logging.DEBUG, logger=f"global.controllers.{sh.name}"):
        sh.open()
        assert sh.state == TangoShutterState.DISABLE
    assert "ignored" in caplog.messages[-1]
    with caplog.at_level(logging.DEBUG, logger=f"global.controllers.{sh.name}"):
        sh.close()
        assert sh.state == TangoShutterState.DISABLE
    assert "ignored" in caplog.messages[-1]
