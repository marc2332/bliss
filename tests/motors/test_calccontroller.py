# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common.axis import Axis
from bliss.common.standard import ascan


def test_tags(s1ho):
    controller = s1ho.controller
    for tag, axis_name in {
        "front": "s1f",
        "back": "s1b",
        "up": "s1u",
        "down": "s1d",
        "hgap": "s1hg",
        "hoffset": "s1ho",
        "vgap": "s1vg",
        "voffset": "s1vo",
    }.iteritems():
        assert controller._tagged[tag][0].name == axis_name


def test_real_tags(s1ho):
    controller = s1ho.controller
    assert [x.name for x in controller._tagged["real"]] == ["s1f", "s1b", "s1u", "s1d"]


def test_has_tag(s1ho, s1vg, s1u):
    assert s1ho.has_tag("hoffset")
    assert not s1ho.has_tag("vgap")
    assert not s1vg.has_tag("real")


def test_reals_list(s1ho):
    controller = s1ho.controller
    assert len(controller.reals) == 4
    assert all([isinstance(x, Axis) for x in controller.reals])


def test_pseudos_list(s1ho):
    controller = s1ho.controller
    assert len(controller.pseudos) == 4
    assert all([isinstance(x, Axis) for x in controller.pseudos])


def test_exported_pseudo_axes(s1vg, s1vo, s1hg, s1ho):
    assert all((s1vg, s1vo, s1hg, s1ho))
    controller = s1vg.controller
    assert all((axis.controller == controller for axis in (s1vg, s1vo, s1hg, s1ho)))
    assert all(["READY" in axis.state() for axis in controller.pseudos])


def test_real_axis_is_right_object(s1f, s1ho, m1):
    controller = s1ho.controller
    assert s1f == controller.axes["s1f"]
    assert s1f.controller == m1.controller


def test_calc_with_init(roby, calc_mot1):
    # see issue #488
    # calc_mot1 defines some attribute in 'initialize_axis',
    # the next two lines should pass without exception:
    roby.position()
    roby.sync_hard()


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
        assert s1hg._set_position() == pytest.approx(s1hg.position())
    finally:
        s1f.controller.set_hw_limits(s1f, None, None)
        s1b.controller.set_hw_limits(s1b, None, None)


def test_real_move_and_set_pos(s1f, s1b, s1hg):
    s1hg.move(0.5)
    s1f.rmove(1)
    s1b.rmove(1)
    assert s1f._set_position() == pytest.approx(1.25)
    assert s1b._set_position() == pytest.approx(1.25)
    assert s1hg.position() == pytest.approx(2.5)
    assert s1hg._set_position() == pytest.approx(2.5)


def test_set_dial(roby, calc_mot1):
    calc_mot1.move(4)
    assert roby.position() == pytest.approx(2)
    calc_mot1.dial(0)
    assert calc_mot1.position() == pytest.approx(4)
    assert calc_mot1.dial() == pytest.approx(0)
    assert roby.position() == pytest.approx(0)


def test_set_position(roby, calc_mot1):
    calc_mot1.move(1)
    assert calc_mot1.offset == pytest.approx(0)
    assert roby.position() == pytest.approx(0.5)
    calc_mot1.position(0)
    assert calc_mot1.offset == pytest.approx(-1)
    assert calc_mot1.position() == pytest.approx(0)
    assert calc_mot1.dial() == pytest.approx(1)
    assert roby.position() == pytest.approx(0.5)


def test_offset_set_position(calc_mot1):
    calc_mot1.dial(0)
    calc_mot1.position(1)
    assert calc_mot1._set_position() == pytest.approx(1)
    calc_mot1.move(0.1)
    assert calc_mot1._set_position() == pytest.approx(0.1)


def test_calc_in_calc(roby, calc_mot1, calc_mot2):
    calc_mot1.move(1)
    assert calc_mot1.position() == pytest.approx(1)
    assert roby.position() == pytest.approx(0.5)
    calc_mot2.move(1)
    assert calc_mot1.position() == pytest.approx(0.5)
    assert calc_mot2.position() == pytest.approx(1)
    assert roby.position() == pytest.approx(0.25)


def test_ascan_limits(s1hg, s1f, s1b):
    s1hg.position(0)
    s1hg.dial(0)
    s1f.limits(-1, 1)
    s1b.limits(-1, 1)
    assert pytest.raises(ValueError, "s1hg.move(2.1)")
    assert pytest.raises(ValueError, "ascan(s1hg, -1, 2.1, 10, 0.1, run=False)")
