# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import subprocess
import sys
import os

@pytest.fixture(scope="module")
def session99():
    session_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_configuration', 'sessions', 'session99.yml'))
    session_setup_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_configuration', 'sessions', 'session99_setup.py'))
    session_scripts_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_configuration', 'sessions', 'scripts', 'session99.py'))
    yield (session_file, session_setup_file, session_scripts_file)
    for filename in (session_file, session_setup_file, session_scripts_file):
        try:
            os.unlink(filename)
        except OSError:
            pass

def test_create_session(beacon, session99):
    session_file, session_setup_file, session_scripts_file = session99
    bliss_shell = subprocess.Popen(['bliss', '-c', 'session99'], stdout=subprocess.PIPE)
    bliss_shell.wait()
    assert os.path.exists(session_file)
    assert os.path.exists(session_setup_file)
    assert os.path.exists(session_scripts_file)

def test_delete_session(beacon, session99):
    session_file, session_setup_file, session_scripts_file = session99
    bliss_shell = subprocess.Popen(['bliss', '-d', 'session99'], stdout=subprocess.PIPE)
    bliss_cmd_output = bliss_shell.communicate()
    assert not os.path.exists(session_file)
    assert not os.path.exists(session_setup_file)
    assert not os.path.exists(session_scripts_file)

