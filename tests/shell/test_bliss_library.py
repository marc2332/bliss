# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2017 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import subprocess
import gevent
import os


ROOT = os.path.dirname(__file__)


def test_library_script(beacon):
    script = subprocess.Popen(
        ["python", os.path.join(ROOT, "check_library_mode_script.py")],
        stdout=subprocess.PIPE,
    )

    output, err = script.communicate()

    assert script.returncode == 0, output
    assert b"bliss.shell" not in output, output
    assert b"SHELL_MODE: False" in output, output


def test_shell_script(beacon):
    script = subprocess.Popen(
        ["python", os.path.join(ROOT, "check_shell_mode_script.py")],
        stdout=subprocess.PIPE,
    )

    output, err = script.communicate()

    assert script.returncode == 0, output
    assert b"SHELL_MODE: True" in output, output


def test_shell_quit(beacon, ports):
    my_env = os.environ.copy()
    my_env["BEACON_HOST"] = f"localhost:{ports.beacon_port}"
    script = subprocess.Popen(
        ["python", os.path.join(ROOT, "check_shell_quit.py")], env=my_env
    )

    try:
        with gevent.Timeout(5):
            script.communicate()
    except gevent.Timeout:
        raise RuntimeError("Session could not be terminated") from None


def test_sync_lib_mode(capsys, default_session):
    """stdout should not have anything"""
    commands = (
        "from bliss.shell.standard import sync",
        "from bliss.config import static",
        "config = static.get_config()",
        "roby = config.get('roby')",
        "sync(roby)",
    )

    script = subprocess.Popen(
        ["python", "-c", ";".join(commands)], stdout=subprocess.PIPE
    )

    output, err = script.communicate()

    assert b"Forcing axes synchronization with hardware" not in output, output
    assert script.returncode == 0, output
    assert len(output) == 0, output
