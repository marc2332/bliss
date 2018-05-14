# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import sys
import os

from bliss import release
from bliss.common import subprocess
from bliss.common.session import Session
from bliss.shell.cli.main import get_sessions_list
from bliss.shell.cli.main import print_sessions_and_trees
from bliss.shell.cli.main import print_sessions_list


@pytest.fixture(scope="module")
def session99():
    session_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_configuration', 'sessions', 'session99.yml'))
    session_setup_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_configuration', 'sessions', 'session99_setup.py'))
    session_scripts_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_configuration', 'sessions', 'scripts', 'session99.py'))
    yield (session_file, session_setup_file, session_scripts_file)

    # Executed at end of tests of this module.
    for filename in (session_file, session_setup_file, session_scripts_file):
        try:
            os.unlink(filename)
        except OSError:
            pass


def test_print_sessions(beacon):
    bliss_shell = subprocess.Popen(['bliss', '--show-sessions-only'], stdout=subprocess.PIPE)
    bliss_cmd_output, _ = bliss_shell.communicate()

    assert set(bliss_cmd_output.split('\n')) == set("""test_session4
test_session2
test_session5
flint
test_session3
lima_test_session
test_session
freddy
""".split('\n'))


def test_print_version(beacon):
    bliss_shell = subprocess.Popen(['bliss', '--version'], stdout=subprocess.PIPE)
    out, _ = bliss_shell.communicate()
    assert out.strip().endswith(release.short_version)


def test_invalid_arg(beacon):
    print_sessions_and_trees(get_sessions_list())

    # invalid argument
    assert subprocess.call(["bliss", "-z"]) == 1


def test_create_session(beacon, session99):
    session_file, session_setup_file, session_scripts_file = session99
    bliss_shell = subprocess.Popen(['bliss', '-c', 'session99'], stdout=subprocess.PIPE)
    bliss_shell.wait()
    assert os.path.exists(session_file)
    assert os.path.exists(session_setup_file)
    assert os.path.exists(session_scripts_file)

    beacon.reload()
    sess = beacon.get("session99")
    assert isinstance(sess, Session)


def test_delete_session(beacon, session99):
    session_file, session_setup_file, session_scripts_file = session99
    bliss_shell = subprocess.Popen(['bliss', '-d', 'session99'], stdout=subprocess.PIPE)
    bliss_cmd_output = bliss_shell.communicate()
    assert not os.path.exists(session_file)
    assert not os.path.exists(session_setup_file)
    assert not os.path.exists(session_scripts_file)
