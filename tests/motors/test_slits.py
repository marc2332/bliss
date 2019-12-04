# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent
from bliss.common.axis import Axis


def test_pseudo_axes_position(s1f, s1b, s1u, s1d, s1vg, s1vo, s1hg, s1ho):
    s1f.position = 0
    s1b.position = 1
    s1u.position = 0
    s1d.position = 1
    assert s1vg.position == 1
    assert s1hg.position == 1
    assert s1vo.position == -0.5
    assert s1ho.position == -0.5


def test_pseudo_axes_move(s1b, s1f, s1hg, s1ho):
    s1hg.move(0.5)
    assert s1hg.position == pytest.approx(0.5)
    hgap = s1hg.position
    s1ho.move(2)
    assert s1b.state.READY
    assert s1f.state.READY
    assert s1hg.position == pytest.approx(hgap)
    assert s1ho.position == pytest.approx(2)
    assert s1b.position == pytest.approx((hgap / 2.0) - 2)
    assert s1f.position == pytest.approx((hgap / 2.0) + 2)


def test_pseudo_axis_scan(s1ho, s1b, s1f, s1hg):
    hgap = 0.5
    s1hg.move(hgap)

    # scan the slits under the motors resolution
    ho_step = (1.0 / s1b.steps_per_unit) / 10.0
    for i in range(100):
        s1ho.rmove(ho_step)

    assert s1hg.position == pytest.approx(hgap)


def test_keep_zero_offset(s1hg, s1b, s1f):
    s1hg.move(4)
    s1hg.dial = 0
    assert s1hg.position == pytest.approx(0)
    assert s1hg.dial == pytest.approx(0)
    assert s1b.position == pytest.approx(0)
    assert s1f.position == pytest.approx(0)

    s1hg.move(2)
    s1hg.position = 0
    assert s1hg.offset == 0
    assert s1b.position == pytest.approx(0)
    assert s1f.position == pytest.approx(0)


def test_limits(s1hg):
    with pytest.raises(ValueError):
        s1hg.move(40)
    with pytest.raises(ValueError):
        s1hg.move(-16)


def test_hw_limits_and_set_pos(s1f, s1b, s1hg):
    try:
        s1f.controller.set_hw_limits(s1f, -2, 2)
        s1b.controller.set_hw_limits(s1b, -2, 2)
        with pytest.raises(RuntimeError):
            s1hg.move(6)
        assert s1hg._set_position == pytest.approx(s1hg.position)
    finally:
        s1f.controller.set_hw_limits(s1f, None, None)
        s1b.controller.set_hw_limits(s1b, None, None)


def test_real_move_and_set_pos(s1f, s1b, s1hg):
    s1hg.move(0.5)
    s1f.rmove(1)
    s1b.rmove(1)
    assert s1f._set_position == pytest.approx(1.25)
    assert s1b._set_position == pytest.approx(1.25)
    assert s1hg.position == pytest.approx(2.5)
    assert s1hg._set_position == pytest.approx(2.5)


def test_offset_set_position(s1hg):
    s1hg.dial = 0
    s1hg.position = 1
    assert s1hg._set_position == pytest.approx(1)
    s1hg.move(0.1)
    assert s1hg._set_position == pytest.approx(0.1)
