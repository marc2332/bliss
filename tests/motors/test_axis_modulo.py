# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
from bliss.common import event


def test_axis_modulo(omega):
    omega.move(10)
    assert omega.position == pytest.approx(10)
    omega.move(361)
    assert omega.position == pytest.approx(1)
    assert omega.dial == pytest.approx(1)
    omega.move(-180)
    assert omega.position == pytest.approx(180)
    omega.position = 0
    assert omega.position == pytest.approx(0)
    assert omega.dial == pytest.approx(180)
    omega.dial = 0
    assert omega.position == pytest.approx(0)
    assert omega.dial == pytest.approx(0)
    omega.move(361)
    assert omega.position == pytest.approx(1)
    assert omega.dial == pytest.approx(1)
    omega.move(0)
    assert omega.position == pytest.approx(0)
    assert omega.dial == pytest.approx(0)
