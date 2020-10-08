# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.scans import ct
import numpy


def test_bpm_read_all(session, lima_simulator2, mocker):
    """White box test to check if each counters is at the right place"""
    bpm = session.config.get("bpm2")
    # BPM data are : timestamp, intensity, center_x, center_y, fwhm_x, fwhm_y, frameno
    from_device = numpy.array([10, 20, 30, 40, 50, 60, 70])
    mocker.patch.object(bpm, "_snap_and_get_results", return_value=from_device)

    # Test all counters together
    all_result = bpm.raw_read()
    all_result = numpy.array(all_result)[:, 0]
    numpy.testing.assert_allclose(all_result, from_device[:-1])

    # Test single one
    for counter in bpm.counters:
        assert bpm.read_all(counter) == [from_device[counter.value_index]]


def test_ebv(session, lima_simulator2, clean_gevent, flint_session):
    clean_gevent["end-check"] = False
    bv1 = session.config.get("bv1")

    data = bv1.bpm.raw_read()
    assert len(data) == 6

    s = ct(1., bv1)
    assert s.get_data()["acq_time"]
    assert s.get_data()["fwhm_x"]
    assert s.get_data()["fwhm_y"]
    assert s.get_data()["x"]
    assert s.get_data()["y"]
    assert s.get_data()["intensity"]
    assert s.get_data()["ebv_diode"]

    bv1.bpm.snap()

    # test for issue 2023
    assert bv1.wago_controller


def test_bpm(session, lima_simulator2):
    bpm = session.config.get("bpm2")
    data = bpm.raw_read()
    assert len(data) == 6
    s = ct(1., bpm)
    assert s.get_data()["acq_time"]
    assert s.get_data()["fwhm_x"]
    assert s.get_data()["fwhm_y"]
    assert s.get_data()["x"]
    assert s.get_data()["y"]
    assert s.get_data()["intensity"]
