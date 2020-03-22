# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from bliss.common.logtools import logbook_printer


@pytest.fixture
def log_shell_mode():
    logbook_printer.add_stdout_handler()
    yield
    logbook_printer.remove_stdout_handler()


def test_axis_lprint(roby, capsys, log_shell_mode):
    move_user_msg = roby.prepare_move(0.1).user_msg

    roby.move(0.1)

    assert capsys.readouterr().out == move_user_msg + "\n"

    roby.position = 0

    assert (
        capsys.readouterr().out
        == "Resetting 'roby` position from 0.1 to 0.0 (sign: 1, offset: -0.1)\n"
    )

    roby.dial = 1

    assert capsys.readouterr().out == "Resetting 'roby` dial position from 0.1 to 1.0\n"

    roby.position = roby.dial = 2

    assert (
        capsys.readouterr().out
        == "Resetting 'roby` position from 0.0 to 2.0 (sign: 1, offset: 1.0)\nResetting 'roby` dial position from 1.0 to 2.0\n"
    )
