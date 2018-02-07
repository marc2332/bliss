# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import time
import gevent
import gevent.event
from bliss.common import event

def test_axis_modulo(omega):
    omega.move(10)
    assert pytest.approx(omega.position(), 10)
    omega.move(361)
    assert pytest.approx(omega.position(), 1)
    assert pytest.approx(omega.dial(), 1)
    omega.move(-180)
    assert pytest.approx(omega.position(), 180)
    omega.position(0)
    assert pytest.approx(omega.position(), 0)
    assert pytest.approx(omega.dial(), 180)
    omega.dial(0)
    assert pytest.approx(omega.position(), 0)
    assert pytest.approx(omega.dial(), 0)
    omega.move(361)
    assert pytest.approx(omega.position(), 1)
    assert pytest.approx(omega.dial(), 1)
    print omega.dial()
    print omega._hw_position()
    omega.move(0)
    assert pytest.approx(omega.position(), 0)
    assert pytest.approx(omega.dial(), 0)



