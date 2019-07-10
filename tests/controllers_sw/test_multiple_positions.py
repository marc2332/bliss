# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_multiple_positions(beacon):
    """ Test MultiplePositions object.
    beamstop has 2 positions: IN and OUT
    """
    beamstop = beacon.get("beamstop")
    mot1 = beacon.get("roby")
    mot2 = beacon.get("robz")

    # Test moving by label to a position.
    beamstop.move("IN")
    assert beamstop.position == "IN"

    # Test configuration validity.
    for mot in beamstop.targets_dict["IN"]:
        mot_min = mot["destination"] - mot["tolerance"]
        mot_max = mot["destination"] + mot["tolerance"]
        print(mot_min, mot_max)
        assert mot_min < mot["axis"].position < mot_max
        assert beamstop._in_position(mot)

    # Test moving by label to a wrong position.
    with pytest.raises(RuntimeError):
        beamstop.move("TOTO")

    # Test moving real motors to an exact valid position.
    mot1.move(3.5)
    mot2.move(2.0)
    assert beamstop.position == "OUT"

    # Test state is READY after a move.
    assert beamstop.state == "READY"

    # Test state is not READY during a move.
    # TODO ???

    # Test moving real motors to an aproximative valid position
    # (half of the tolerance is added to each target).
    mot1.move(2.5 + beamstop.targets_dict["IN"][0]["tolerance"] / 2)
    mot2.move(1.0 + beamstop.targets_dict["IN"][1]["tolerance"] / 2)
    assert beamstop.position == "IN"

    # Test moving real motors to an invalid position.
    mot1.move(0.0)
    mot2.move(0.0)
    assert beamstop.position == "unknown"

    # test timeout
    beamstop.move("OUT", wait=False)
    with pytest.raises(RuntimeError) as info:
        beamstop.wait(0.05)
    assert str(info.value) == "Timeout while waiting for motors to move"


def test_multiple_positions_add_remove(beacon):
    """ Test MultiplePositions object.
    beamstop has 2 positions: IN and OUT
    """
    beamstop = beacon.get("beamstop")
    mot1 = beacon.get("roby")
    mot2 = beacon.get("robz")

    assert len(beamstop.targets_dict) == 2

    # Create a new position
    beamstop.create_position("HALF_IN", [(mot1, 4), (mot2, 5)], "half in half out")

    assert len(beamstop.targets_dict) == 3

    # Should not be able to create twice the same position.
    with pytest.raises(RuntimeError):
        beamstop.create_position("HALF_IN", [(mot1, 4), (mot2, 5)], "half in half out")

    assert len(beamstop.targets_dict) == 3

    # REMOVE
    beamstop.remove_position("HALF_IN")
    assert len(beamstop.targets_dict) == 2
