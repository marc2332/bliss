# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import subprocess
import gevent
import os


def execute_in_subprocess(command):
    script = subprocess.Popen(
        ["python", "-c", command], stderr=subprocess.PIPE, stdout=subprocess.PIPE
    )

    output, err = script.communicate()
    returncode = script.returncode
    return output.decode(), err.decode(), returncode

ROOT = os.path.dirname(__file__)


def test_library_script(beacon):
    # suppress warnings as we test output
    script = subprocess.Popen(
        ["python", "-W ignore", os.path.join(ROOT, "check_library_mode_script.py")],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    output, err = script.communicate()

    assert script.returncode == 0
    assert err == b""
    assert b"bliss.shell" not in output
    assert b"SHELL_MODE: False" in output


def test_shell_script(beacon):
    # suppress warnings as we test output
    script = subprocess.Popen(
        ["python", "-W ignore", os.path.join(ROOT, "check_shell_mode_script.py")],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    output, err = script.communicate()

    assert script.returncode == 0
    assert err == b""
    assert b"SHELL_MODE: True" in output


def test_shell_quit(beacon, ports):
    my_env = os.environ.copy()
    my_env["BEACON_HOST"] = f"localhost:{ports.beacon_port}"
    script = subprocess.Popen(
        ["python", os.path.join(ROOT, "check_shell_quit.py")],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env=my_env,
    )

    try:
        with gevent.Timeout(5):
            output, err = script.communicate()
    except gevent.Timeout:
        raise RuntimeError("Session could not be terminated")


def test_sync_lib_mode(capsys, default_session):
    """stdout should not have anything"""
    commands = (
        "from bliss.shell.standard import sync",
        "from bliss.config import static",
        "config = static.get_config()",
        "roby = config.get('roby')",
        "sync(roby)",
    )

    output, err, returncode = execute_in_subprocess(";".join(commands))

    assert "Forcing axes synchronization with hardware" not in output

    assert returncode == 0
    assert len(output) == 0
