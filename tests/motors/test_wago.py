# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common.axis import AxisState


def test_wago_motor(session):
    dacm1 = session.config.get("dacm1")
    pos = 300
    dacm1.move(pos)
    assert pos == pytest.approx(dacm1.position, 1)
    pos = 2000
    dacm1.move(pos)
    assert pos == pytest.approx(dacm1.position, 1)
    dacm1.state == AxisState("READY")

    dacm2 = session.config.get("dacm1")
    pos = 5000
    dacm2.move(pos)
    assert pos == pytest.approx(dacm2.position, 1)
    pos = 7000
    dacm2.move(pos)
    assert pos == pytest.approx(dacm2.position, pos)
    dacm2.state == AxisState("READY")


def test_wago_motor_limits(session):
    dacm1 = session.config.get("dacm1")
    with pytest.raises(ValueError):
        dacm1.move(20000)
    with pytest.raises(ValueError):
        dacm1.move(-1)
