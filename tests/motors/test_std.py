# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.common.standard import mv, mvr


def test_mv(roby):
    mv(roby, 2)
    assert roby.position == pytest.approx(2)


def test_mvr(roby):
    p1 = roby.position
    mvr(roby, 1)
    assert roby.position == pytest.approx(p1 + 1)


def test_group_mv(roby, robz):
    mv(roby, 3, robz, 1)
    assert roby.position == pytest.approx(3)
    assert robz.position == pytest.approx(1)


def test_interrupted_mv(roby):
    mv_task = gevent.spawn(mv, roby, 1000)
    gevent.sleep(0.1)
    mv_task.kill()
    assert "READY" in roby.state
    assert roby.position == roby._set_position
