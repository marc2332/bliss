# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

import numpy

from bliss import setup_globals
from bliss.common.standard import SoftAxis, SoftCounter, ascan


class Object(object):

    stopped = 0
    nb_pos_read = 0
    nb_pos_write = 0
    nb_move = 0
    nb_stop = 0

    @property
    def position(self):
        self.nb_pos_read += 1
        return self._position

    @position.setter
    def position(self, pos):
        self.nb_pos_write += 1
        self._position = pos

    def move_me(self, position):
        self.nb_move += 1
        self._position = position


def test_soft_axis_creation(beacon):

    o0 = Object()
    o0.position = 1.2345
    assert o0.nb_pos_write == 1

    m0 = SoftAxis("a_unique_motor", o0)

    assert m0.name == "a_unique_motor"
    assert hasattr(setup_globals, m0.name)

    assert m0.position == o0.position
    assert o0.nb_pos_read == 2
    assert o0.nb_pos_write == 1
    assert o0.nb_move == 0

    m0.move(45.54)
    assert o0.position == 45.54
    assert m0.position == o0.position
    assert o0.nb_pos_read >= 4
    assert o0.nb_pos_write == 2
    assert o0.nb_move == 0

    m1 = SoftAxis("a_second_motor", o0, move="move_me")

    m1.move(-12.23)
    assert o0.position == -12.23
    assert m1.position == o0.position
    assert o0.nb_pos_read >= 6
    assert o0.nb_pos_write == 2
    assert o0.nb_move == 1

    nb_pos_read = o0.nb_pos_read

    m2 = SoftAxis("a_third_motor", o0, position="_position", move=o0.move_me)

    m2.move(456.789)
    assert o0.position == 456.789
    assert m2.position == o0.position
    assert o0.nb_pos_read == nb_pos_read + 2
    assert o0.nb_pos_write == 2
    assert o0.nb_move == 2


def test_soft_axis_scan(session):

    o0 = Object()
    o0.position = 1.2345

    m0 = SoftAxis("another_motor", o0)
    c0 = SoftCounter(o0, value="position", name="motor_counter")

    scan = ascan(m0, -200, 200, 99, 0.001, c0)

    data = scan.get_data()

    positions = numpy.linspace(-200, 200, 100)
    numpy.testing.assert_array_almost_equal(data["motor_counter"], positions)
    numpy.testing.assert_array_almost_equal(data["another_motor"], positions)
