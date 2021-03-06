# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import subprocess
import pytest
import sys
import os

from bliss import release
from bliss.common.session import Session
from bliss.shell.main import get_sessions_list
from bliss.shell.main import print_sessions_and_trees
from bliss.shell.main import print_sessions_list


BLISS = [sys.executable, "-m", "bliss.shell.main"]


@pytest.fixture
def session99(beacon_directory):
    session_file = os.path.join(beacon_directory, "sessions", "session99.yml")
    session_setup_file = os.path.join(
        beacon_directory, "sessions", "session99_setup.py"
    )
    session_scripts_file = os.path.join(
        beacon_directory, "sessions", "scripts", "session99.py"
    )
    init_file = os.path.join(os.path.dirname(session_file), "__init__.yml")
    os.rename(init_file, os.path.join(os.path.dirname(session_file), "__init__.sav"))

    yield (session_file, session_setup_file, session_scripts_file, init_file)

    # Executed at end of tests of this module.
    os.rename(os.path.join(os.path.dirname(session_file), "__init__.sav"), init_file)
    for filename in (session_file, session_setup_file, session_scripts_file):
        try:
            os.unlink(filename)
        except OSError:
            pass


def test_print_sessions(beacon):
    bliss_shell = subprocess.Popen(
        BLISS + ["--show-sessions-only"], stdout=subprocess.PIPE, text=True
    )
    bliss_cmd_output, _ = bliss_shell.communicate()

    assert set(bliss_cmd_output.split("\n")) == set(
        """
failing_setup_session
flint
freddy
lima_test_session
nexus_writer_session
scan_saving_test_session
test_alias
test_alias2
test_autof_session
test_exceptions_session
test_logging_session
test_session
test_session2
test_session3
test_session4
test_session5
""".split(
            "\n"
        )
    )


def test_print_version(beacon):
    bliss_shell = subprocess.Popen(
        BLISS + ["--version"], stdout=subprocess.PIPE, text=True
    )
    out, _ = bliss_shell.communicate()
    assert out.strip().endswith(release.short_version)


def test_invalid_arg(beacon):
    print_sessions_and_trees(get_sessions_list())

    # invalid argument
    assert subprocess.call(["bliss", "-z"]) == 1


def test_create_then_delete_session(beacon, session99):
    session_file, session_setup_file, session_scripts_file, init_file = session99
    bliss_shell = subprocess.Popen(BLISS + ["-c", "session99"], stdout=subprocess.PIPE)
    bliss_shell.wait()
    assert os.path.exists(init_file)
    assert open(init_file).read() == "plugin: session\n"
    assert os.path.exists(session_file)
    assert os.path.exists(session_setup_file)
    assert os.path.exists(session_scripts_file)

    beacon.reload()
    sess = beacon.get("session99")
    assert isinstance(sess, Session)

    bliss_shell = subprocess.Popen(
        BLISS + ["-D", "session99"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    bliss_shell.communicate(input=b"yes\n")
    assert not os.path.exists(session_file)
    assert not os.path.exists(session_setup_file)
    assert not os.path.exists(session_scripts_file)
