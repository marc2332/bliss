# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest


def test_stackmotor_on(session):
    mstack = session.config.get("mstack")
    roby = session.config.get("roby")
    m2 = session.config.get("m2")

    # activate stack
    mstack.stack_on()

    small_move = 0.1
    big_move = 2
    pos_mstack = mstack.position
    pos_roby = roby.position
    pos_m2 = m2.position

    # small move => small motor moved (m2)
    mstack.move(small_move, relative=True)
    assert pytest.approx(mstack.position) == pos_mstack + small_move
    assert pytest.approx(roby.position) == pos_roby
    assert pytest.approx(m2.position) == pos_m2 + small_move

    # big move => big motor moved (roby) + small motor moved back to middle position (m2)
    mstack.move(big_move, relative=True)
    assert pytest.approx(mstack.position) == pos_mstack + small_move + big_move
    assert pytest.approx(roby.position) == pos_roby + small_move + big_move
    assert pytest.approx(m2.position) == pos_m2


def test_stackmotor_off(session):
    mstack = session.config.get("mstack")
    roby = session.config.get("roby")
    m2 = session.config.get("m2")

    small_move = 0.1
    pos_mstack = mstack.position
    pos_roby = roby.position
    pos_m2 = m2.position

    # deactivate stack
    mstack.stack_off()

    # small move => small motor doesn't move
    mstack.move(small_move, relative=True)
    assert pytest.approx(mstack.position) == pos_mstack + small_move
    assert pytest.approx(roby.position) == pos_roby + small_move
    assert pytest.approx(m2.position) == pos_m2
