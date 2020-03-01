# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.controllers.transfocator import Transfocator


def test_transfocator(default_session):
    transfocator = default_session.config.get("transfocator_simulator")
    transfocator.connect()
    # only reading is possible due to simulator limitations
    transfocator.status_read()
    transfocator.status_dict()


def test_transfocator_inout(default_session):
    transfocator = default_session.config.get("transfocator_simulator")
    transfocator[:] = 0
    assert transfocator.pos_read() == 0
    assert (
        transfocator.__info__()
        == "Transfocator transfocator_simulator:\nP0   L1   L2   L3   L4   L5   L6   L7   L8\nOUT  OUT  OUT  OUT  OUT  OUT  OUT  OUT  OUT"
    )

    transfocator[:] = 1
    assert transfocator.pos_read() == 0b111111111
    assert (
        transfocator.__info__()
        == "Transfocator transfocator_simulator:\nP0  L1  L2  L3  L4  L5  L6  L7  L8\nIN  IN  IN  IN  IN  IN  IN  IN  IN"
    )

    transfocator.set_all(False)
    assert transfocator.pos_read() == 0
    transfocator.set_all()
    assert transfocator.pos_read() == 0b111111111
    transfocator.set_pin(False)
    assert transfocator.pos_read() == 0b111111110
