# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from bliss.common.scans import loopscan, ct
from bliss.common.counter import SoftCounter, SamplingMode
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave


def test_axis_lprint(roby, capsys, log_shell_mode):
    move_user_msg = roby.prepare_move(0.1).user_msg

    roby.move(0.1)

    assert capsys.readouterr().out == move_user_msg + "\n"

    roby.position = 0

    assert (
        capsys.readouterr().out
        == "Resetting 'roby` position from 0.1 to 0.0 (new offset: -0.1)\n"
    )

    roby.dial = 1

    assert (
        capsys.readouterr().out
        == "Resetting 'roby` dial position from 0.1 to 1.0 (new offset: -1.0)\n"
    )

    roby.position = roby.dial = 2

    assert (
        capsys.readouterr().out
        == "Resetting 'roby` position from 0.0 to 2.0 (new offset: 1.0)\nResetting 'roby` dial position from 1.0 to 2.0 (new offset: 0.0)\n"
    )
