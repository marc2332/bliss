# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from unittest import mock
from bliss.common.axis import AxisState, AxisOnLimitError


def test_axis_stdout(roby, capsys, log_shell_mode):
    move_user_msg = roby.get_motion(0.1).user_msg

    roby.move(0.1)

    assert capsys.readouterr().out == move_user_msg + "\n"

    roby.position = 0

    assert (
        capsys.readouterr().out
        == "'roby` position reset from 0.1 to 0.0 (sign: 1, offset: -0.1)\n"
    )

    roby.dial = 1

    assert capsys.readouterr().out == "'roby` dial position reset from 0.1 to 1.0\n"

    roby.position = roby.dial = 2

    assert (
        capsys.readouterr().out
        == "'roby` position reset from 0.0 to 2.0 (sign: 1, offset: 1.0)\n'roby` dial position reset from 1.0 to 2.0\n"
    )


def test_axis_stdout2(roby, bad_motor, capsys, log_shell_mode):
    """Ensure "Moving..." and "...stopped at..." messages are present.
    """
    roby.move(0.1)

    out, err = capsys.readouterr()
    assert "Moving roby from 0 to 0.1\n" in out

    roby.move(0.2, wait=False)
    roby.stop()

    out, err = capsys.readouterr()
    assert "Axis roby stopped at position" in out


def test_axis_stderr1(roby):
    with mock.patch.object(roby.controller, "state") as new_state:
        new_state.return_value = AxisState("READY", "LIMNEG")
        assert roby.state.LIMNEG
        with pytest.raises(
            AxisOnLimitError,
            match=r"roby: READY \(Axis is READY\) \| "
            r"LIMNEG \(Hardware low limit active\) at [0-9\.]*",
        ):
            roby.jog()
            roby.stop()
