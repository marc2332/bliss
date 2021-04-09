# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import bliss.comm.modbus


def test_eurotherm_init(beacon, dummy_tango_server, session):
    ok = False
    try:
        loop = beacon.get("euro_loop")
        loop.setpoint
    except bliss.comm.modbus.ModbusError:
        ok = True
    assert ok
