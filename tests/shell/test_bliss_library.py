# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import subprocess


def test_library_script(beacon):
    script = subprocess.Popen(
        ["python", "tests/shell/check_library_mode_script.py"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    output, err = script.communicate()

    assert script.returncode == 0
    assert len(err) == 0
    assert b"bliss.shell" not in output
    assert b"SHELL_MODE: False" in output


def test_shell_script(beacon):
    script = subprocess.Popen(
        ["python", "tests/shell/check_shell_mode_script.py"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    output, err = script.communicate()

    assert script.returncode == 0
    assert len(err) == 0
    assert b"SHELL_MODE: True" in output
