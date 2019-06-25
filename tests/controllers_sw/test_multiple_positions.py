# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_multiple_positions(beacon):
    beamstop = beacon.get("beamstop")

    # test position
    beamstop.move("IN")
    print(beamstop.position)
    assert beamstop.position == "IN"
    for mot in beamstop.motors["IN"]:
        mot_min = mot["target"] - mot["delta"]
        mot_max = mot["target"] + mot["delta"]
        print(mot_min, mot_max)
        assert mot_min < mot["axis"].position < mot_max
        assert beamstop._in_position(mot)

    # test timeout
    beamstop.move("OUT", wait=False)
    with pytest.raises(RuntimeError) as info:
        beamstop.wait("OUT", 0.05)
    assert str(info.value) == "Timeout while waiting for motors to move"
