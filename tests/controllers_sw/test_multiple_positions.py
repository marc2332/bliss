# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.controllers import multiplepositions


def test_multiple_positions(session):
    """ Test MultiplePositions object.
    beamstop has 2 positions: IN and OUT
    """
    beamstop = session.env_dict.get("beamstop")
    mot1 = session.env_dict.get("roby")
    mot2 = session.env_dict.get("robz")

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

    # Test status property (via __info__)
    print(beamstop.__info__())

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

    # Test timeout.
    beamstop.move("OUT", wait=False)
    with pytest.raises(RuntimeError) as info:
        beamstop.wait(0.05)
    assert str(info.value) == "Timeout while waiting for motors to move"

    # Test stop.
    beamstop.move("OUT", wait=False)
    beamstop.stop()

    # Test various motors list properties.
    print(beamstop.motors)
    print(beamstop.motor_names)
    print(beamstop.motor_objs)

    # For coverage
    print(beamstop._state_as_motor())


def test_multiple_positions_add_remove_update(session):
    """ Test MultiplePositions object.
    beamstop has 2 positions: IN and OUT
    """
    beamstop = session.env_dict.get("beamstop")
    mot1 = session.env_dict.get("roby")
    mot2 = session.env_dict.get("robz")

    assert len(beamstop.targets_dict) == 2

    # CREATE
    # Ok to create a new position.
    beamstop.create_position("HALF_IN", [(mot1, 4), (mot2, 5)], "half in half out")

    assert len(beamstop.targets_dict) == 3

    # Should not be able to create twice the same position.
    with pytest.raises(RuntimeError):
        beamstop.create_position("HALF_IN", [(mot1, 4), (mot2, 5)], "half in half out")

    assert len(beamstop.targets_dict) == 3

    # UPDATE
    # ok to update existing position.
    beamstop.update_position("HALF_IN", [(mot1, 4.1), (mot2, 5.1)], "half in half out")
    beamstop.update_position("HALF_IN", description="moit' moit'")

    # motors_destinations_list must be a list.
    with pytest.raises(TypeError):
        beamstop.update_position("HALF_IN", (mot1, 4.1), "half in half out")

    # REMOVE
    beamstop.remove_position("HALF_IN")
    assert len(beamstop.targets_dict) == 2

    # Cannot remove non existing position.
    with pytest.raises(RuntimeError):
        beamstop.remove_position("Totally_IN")


def test_multiple_positions_move_by_label(beacon):
    """Test label-defined move methods
    """

    beamstop = beacon.get("beamstop")
    beamstop.IN()
    assert beamstop.position == "IN"
    beamstop.OUT()
    assert beamstop.position == "OUT"
