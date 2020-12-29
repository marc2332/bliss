# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from unittest import mock
from bliss.common import scans
from bliss.common import encoder as encoder_mod
from bliss.common.encoder import encoder_noise_round
from bliss.controllers.motors.mockup import Mockup


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


@pytest.mark.flaky(reruns=3, reason="issue2353")
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
    assert numpy.array_equal(s.get_data()["m1enc"], [m1enc.read()] * 3)

    m1enc.counter.conversion_function = lambda x: x * 2
    ct = scans.ct(0.1, m1enc)
    assert ct.get_data()["m1enc"] == m1enc.read() * 2


def test_encoder_controller_multiple(default_session, m1, m1enc, m2, m2enc):
    assert m1enc.controller is m2enc.controller
    ## configure to read only once, to check how many times read_all is called
    m1enc.counter.mode = "SINGLE"
    m2enc.counter.mode = "SINGLE"
    ##

    with mock.patch.object(
        m1enc.controller,
        "read_encoder_multiple",
        wraps=m1enc.controller.read_encoder_multiple,
    ) as read_encoder_multiple:
        s = scans.loopscan(1, 0.1, m1enc, m2enc, save=False)

        read_encoder_multiple.assert_called_once_with(m1enc, m2enc)

    data = s.get_data()
    assert data["m1enc"] == m1enc.read()
    assert data["m2enc"] == m2enc.read()


def test_maxee_mode_read_encoder(mot_maxee):
    with mock.patch.object(mot_maxee.encoder, "read") as new_read:
        new_read.return_value = 42.42
        assert mot_maxee.position == 42.42


def test_maxee_mode_set_dial(mot_maxee):
    with mock.patch.object(mot_maxee.encoder, "set") as new_set:
        new_set.return_value = 10.23
        mot_maxee.dial = 10
        assert mot_maxee.dial == 10.23


def test_maxee_mode_simple_move(mot_maxee):
    mot_maxee.move(2)
    assert mot_maxee.position == 2


def test_maxee_mode_check_encoder(mot_maxee):
    # set check_encoder
    mot_maxee.config.set("check_encoder", True)
    with mock.patch.object(mot_maxee.encoder, "read") as new_read:
        new_read.return_value = 12.23
        # motor init
        assert mot_maxee.position == 12.23
        new_read.return_value = 125.12
        with pytest.raises(RuntimeError):
            mot_maxee.move(2)


def test_encoder_filter(default_session, mot_maxee):
    encoder_filter = default_session.config.get("encfilter1")
    encoder = encoder_filter.encoder
    assert encoder.axis == mot_maxee

    mot_maxee.custom_set_measured_noise(6.0)  # big difference compared to motor pos.
    mot_maxee._set_position = 0

    ct = scans.ct(0, encoder_filter)
    data = ct.get_data()
    enc_raw_value = data["encoder:" + encoder.name]
    expected_value = encoder_noise_round(
        enc_raw_value,
        mot_maxee._set_position,
        encoder.steps_per_unit,
        encoder_filter.encoder_precision,
    )
    corrected_value = data["encfilter1:position"]
    assert corrected_value == pytest.approx(expected_value)
    assert data["encfilter1:position_error"] == mot_maxee._set_position - enc_raw_value

    mot_maxee.custom_set_measured_noise(0.1)  # small difference compared to motor pos.
    mot_maxee._set_position = 0
    ct = scans.ct(0, encoder_filter)
    data = ct.get_data()
    enc_raw_value = data["encoder:" + encoder.name]
    expected_value = encoder_noise_round(
        enc_raw_value,
        mot_maxee._set_position,
        encoder.steps_per_unit,
        encoder_filter.encoder_precision,
    )
    corrected_value = data["encfilter1:position"]
    assert (
        corrected_value
        == pytest.approx(expected_value)
        == pytest.approx(mot_maxee._set_position)
    )
