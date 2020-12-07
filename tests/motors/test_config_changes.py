# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import math
import gevent


@pytest.fixture
def robz(robz):
    sign = robz.sign
    spu = robz.steps_per_unit
    ll, hl = robz.dial_limits
    backlash = robz.backlash

    yield robz

    # restore config sign and steps per unit
    robz.config.set("steps_per_unit", spu)
    robz.config.set("sign", sign)
    robz.config.set("low_limit", ll)
    robz.config.set("high_limit", hl)
    robz.config.set("backlash", backlash)
    robz.config.save()


@pytest.mark.parametrize(
    "move_pos, factor, offset, user_sign",
    [
        (1.0, 2, 10., 1),
        (1.0, -1, 0, 1),
        (0, -1, 10, 1),
        (1.0, 2, 10., -1),
        (1.0, -1, 0, -1),
        (0, -1, 10, -1),
    ],
    ids=[
        "double_steps_per_unit_with_offset",
        "steps_per_unit_sign_change",
        "steps_per_unit_sign_change_0_pos_with_offset",
        "double_steps_per_unit_with_offset_and_opposite_user_sign",
        "steps_per_unit_sign_change_and_opposite_user_sign",
        "steps_per_unit_sign_change_0_pos_with_offset_and_opposite_user_sign",
    ],
)
def test_steps_per_unit_modified(robz, move_pos, factor, offset, user_sign):
    spu_0 = robz.steps_per_unit

    # SET THE OFFSET
    robz.position = robz.dial + offset
    assert robz.offset == offset
    assert robz.sign == 1

    # MOVE ROBZ
    robz.move(move_pos)

    # READ VALUES
    values_0 = (
        robz.dial,
        robz.offset,
        robz.position,
        robz._set_position,
        robz.dial_limits,
        robz.limits,
    )

    # CHANGE CONFIG
    robz.config.set("steps_per_unit", robz.steps_per_unit * factor)
    robz.config.set("sign", user_sign)
    robz.config.save()

    # RELOAD CONFIG
    robz.apply_config(reload=True)

    assert robz.sign == user_sign
    assert robz.steps_per_unit == spu_0 * factor

    spu_1 = robz.steps_per_unit

    # CHECK THAT THE POSITIONS ARE UPDATED
    values_1 = (
        robz.dial,
        robz.offset,
        robz.position,
        robz._set_position,
        robz.dial_limits,
        robz.limits,
    )

    if math.copysign(spu_1, spu_0) != spu_1:
        # the sign of steps per unit has changed
        # => dial limits must have been swapped and changed of sign
        l0, h0 = values_0[-2]
        l1, h1 = values_1[-2]
        assert l0 == -h1
        assert h0 == -l1

    assert spu_1 == spu_0 * factor
    assert values_1[0] * factor == values_0[0]  # dial position changes
    assert (
        values_1[1] == values_0[2] - user_sign * values_1[0]
    )  # offset changes to preserve user pos
    assert values_1[2] == values_0[2]  # robz does not change its *user* position
    assert values_1[3] == values_0[3]  # *user* _set_position stays the same


def test_1st_time_cfg_wrong_acc_vel(beacon, beacon_directory):
    m = beacon.get("invalid_acc")

    with pytest.raises(RuntimeError):
        # this will initialize the axis object,
        # and exception will be triggered for
        # acceleration
        m.position

    # change config with good acc
    m.config.set("acceleration", 100)
    m.config.save()

    m.apply_config(reload=True)

    assert m.acceleration == 100

    m = beacon.get("invalid_vel")
    with pytest.raises(RuntimeError):
        m.position
    m.config.set("velocity", 10)
    m.config.save()
    m.apply_config(reload=True)
    assert m.velocity == 10


def test_apply_config_sign_changed(robz):
    assert robz.position == 0
    robz.move(0.1)
    assert robz.position == 0.1
    assert robz.sign == 1
    assert robz.offset == 0

    # change config sign
    robz.config.set("sign", -1)
    robz.config.save()

    # apply config
    robz.apply_config(reload=True)
    assert robz.sign == -1

    # make sure position has been updated according to new sign.
    assert robz.position == -0.1


def test_issue_1520(robz):
    # let's use the same numbers as Frederico
    ypipe = robz
    ypipe.dial = 72.4366
    ypipe.position = 0
    ypipe.limits = -127.4366, 267.5634
    assert ypipe.dial_limits == (-55, 340)
    assert ypipe.offset == -72.4366

    ypipe.settings_to_config()  # save desired limits to config
    # change sign of spu for ypipe in config
    ypipe.config.set("steps_per_unit", -ypipe.steps_per_unit)
    ypipe.config.save()

    ypipe.apply_config(reload=True)

    assert ypipe.position == 0
    assert ypipe.offset == 72.4366  # offset has been changed to keep user pos the same
    assert ypipe.dial_limits == (-340, 55)  # limits swapped and changed of sign

    # set "real" position from ruler (dial) and set user position to 0
    ypipe.dial = 58
    ypipe.dial_limits = 0, 400
    ypipe.position = 0

    assert ypipe.position == 0
    assert ypipe.offset == -58
    assert ypipe.dial == 58
    assert ypipe.dial_limits == (0, 400)
    assert ypipe.limits == (-58, 342)


def test_apply_config_backlash_changed(robz):
    assert robz.backlash == 0
    assert robz.config_backlash == 0

    # change config sign
    robz.config.set("backlash", 1)
    robz.config.save()

    # apply config
    robz.apply_config(reload=True)
    assert robz.config_backlash == 1
    assert robz.backlash == 1

    robz.backlash = 2
    robz.settings_to_config()
    assert robz.config_backlash == 2
