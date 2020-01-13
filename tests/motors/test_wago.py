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
    dacm1.move(3)
    assert 3 == pytest.approx(dacm1.position, .001)
    dacm1.move(5)
    assert 5 == pytest.approx(dacm1.position, .001)
    dacm1.state == AxisState("READY")

    dacm2 = session.config.get("dacm1")
    dacm2.move(2)
    assert 2 == pytest.approx(dacm2.position, .001)
    dacm2.move(7)
    assert 7 == pytest.approx(dacm2.position, .001)
    dacm2.state == AxisState("READY")


def test_wago_motor_limits(session):
    dacm1 = session.config.get("dacm1")
    with pytest.raises(ValueError):
        dacm1.move(20)
    with pytest.raises(ValueError):
        dacm1.move(-1)
