# -*- coding: utf-8 -*-
# This file is part of the bliss project
#
# Copyright (c) 2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Test WhiteBeamAttenuator object."""


def test_white_beam_attenuator(beacon):
    """att1 MultiplePosition and roby Axis object have to be configured."""

    wba = beacon.get("wba")
    roby = beacon.get("roby")

    assert wba.name == "wba"

    # test to move to position
    wba.move(["att1", "Al40"])
    assert wba.position == ["att1", "Al40"]

    # test when move underlying motor
    assert wba.attenuators[0]["attenuator"].motor_objs[0] == roby
    roby.move(0.5)
    assert wba.position == ["att1", "Al"]

    # test with no wait
    wba.move(["att1", "Al40"], wait=False)
    wba.wait(["att1", "Al40"])
    assert wba.position == ["att1", "Al40"]
