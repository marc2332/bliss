# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss.common import scans


def test_get_encoder(m0, m1enc, m1):
    assert m1enc.steps_per_unit == 50
    assert m0.encoder == None
    assert m1.encoder == m1enc


def test_encoder_read(m1, m1enc):
    assert m1enc.read() == m1.dial / m1enc.steps_per_unit


def test_encoder_set(m1enc):
    assert m1enc.set(133) == 133


def test_axis_get_noisy_measured_position(m1):
    try:
        # Switch to noisy mode.
        m1.custom_set_measured_noise(0.1)
        assert abs(m1.dial - m1.dial_measured_position) <= 0.1
    finally:
        # switch back to normal mode.
        m1.custom_set_measured_noise(0.0)


def test_tolerance(m1enc):
    assert m1enc.tolerance == 0.001


def test_maxee(m1):
    # m1enc.read() #make sure encoder is initialized
    try:
        m1.custom_set_measured_noise(0.1)

        with pytest.raises(RuntimeError):
            m1.move(5)
    finally:
        m1.custom_set_measured_noise(0)

    m1.encoder.set(2)
    m1.move(2)
    assert m1.position == 2


def test_move(m1):
    m1.move(5)
    assert m1.position == pytest.approx(m1.encoder.read())


def test_encoder_counter(default_session, m1, m1enc):
    s = scans.loopscan(3, 0.1, m1enc)
    assert numpy.array_equal(s.get_data()["encoder:m1enc:position"], [m1enc.read()] * 3)

    m1enc.counter.conversion_function = lambda x: x * 2
    ct = scans.ct(0.1, m1enc)
    assert ct.get_data()["encoder:m1enc:position"] == m1enc.read() * 2
