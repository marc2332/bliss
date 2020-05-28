# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
from bliss.common.scans import ct


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
