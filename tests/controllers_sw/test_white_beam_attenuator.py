# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Test WhiteBeamAttenuator object."""

import pytest


def test_white_beam_attenuator(beacon, caplog):
    """att1 MultiplePosition and att1z Axis object have to be configured."""

    wba = beacon.get("wba")
    att1z = beacon.get("att1z")

    assert wba.name == "wba"

    # test __info__()
    wba.__info__()

    # test to move to position
    wba.move(["att1", "Al40"])
    assert wba.position == ["att1", "Al40"]

    # test when move underlying motor
    assert wba.attenuators[0]["attenuator"].motor_objs[0] == att1z
    att1z.move(0.5)
    assert wba.position == ["att1", "Al"]

    # test with no wait
    wba.move(["att1", "Al40"], wait=False)
    wba.wait(["att1", "Al40"])
    assert wba.position == ["att1", "Al40"]

    assert caplog.text == ""  # No error messages


def test_faulty_attenuator(beacon, caplog):
    # set to faulty (home switches not activated)
    beacon.get_config("wba").update({"faulty": True})

    wba = beacon.get("wba")
    att1 = beacon.get("att1")

    att1.move("Al", wait=True)

    wba.move(["att1", "Al40"])

    assert "did not start from HOME" in caplog.text
    assert "did not stop on HOME" in caplog.text


def test_frontend_hook(beacon, dummy_tango_server):
    # set a hook to shutter

    fqdn, ds = dummy_tango_server
    beacon.get_config("wba").update({"frontend": "$safshut"})
    sh = beacon.get("safshut")
    wba = beacon.get("wba")
    att1z = beacon.get("att1z")

    wba.move("att1", "Al")

    sh.open()  # moving attenuator is not allowed
    with pytest.raises(RuntimeError):
        wba.move("att1", "Al40")
    sh.close()  # now is ok
    wba.move("att1", "Al40")
    assert len(att1z.motion_hooks) == 1
