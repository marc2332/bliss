# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import subprocess
import gevent
import os


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


def test_shell_quit(beacon, ports):
    my_env = os.environ.copy()
    my_env["BEACON_HOST"] = f"localhost:{ports.beacon_port}"
    script = subprocess.Popen(
        ["python", "tests/shell/check_shell_quit.py"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=my_env,
    )

    try:
        with gevent.Timeout(5):
            output, err = script.communicate()
    except gevent.Timeout:
        raise RuntimeError("Session could not be terminated")
