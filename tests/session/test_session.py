# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import re
from bliss import current_session
from bliss.shell.cli import repl
from bliss import setup_globals
from bliss.common import scans
from treelib import Tree
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput


def test_session_does_not_load_session(session):
    assert getattr(setup_globals, "test_session")
    assert getattr(setup_globals, "test_mg")
    assert pytest.raises(AttributeError, getattr, setup_globals, "freddy")
    assert session == current_session


def test_session_unexisting_object(session2, log_context, caplog):
    """ Ensure that running session2 trig a warning for non existing
    object: 'c_cedille_de_surf'
    """
    session2.setup()
    assert "object 'c_cedille_de_surf' does not exist. Ignoring it." in caplog.text


def test_session_does_not_contain_default_plugin_objs(session):
    assert session.config.get("refs_test")
    assert pytest.raises(AttributeError, getattr, setup_globals, "refs_test")


def test_session_exclude_objects(session):
    assert pytest.raises(AttributeError, getattr, setup_globals, "m2")


def test_current_session(session):
    assert session.env_dict["SESSION_NAME"] == "test_session"


def test_session_tree(session2, capsys):
    session2.sessions_tree.show()
    out1, err1 = capsys.readouterr()
    t = Tree()
    t.create_node("test_session2", "test_session2")
    t.create_node("test_session", "test_session", parent="test_session2")
    t.show()
    out2, err2 = capsys.readouterr()
    assert out1 == out2


def test_include_sessions(session2, capsys):
    assert pytest.raises(AttributeError, getattr, setup_globals, "m0")

    session2.setup()

    out, err = capsys.readouterr()
    out.endswith("TEST_SESSION INITIALIZED\nTEST_SESSION2 INITIALIZED\n")

    assert getattr(setup_globals, "m2")
    assert getattr(setup_globals, "m0")
    assert current_session.name == setup_globals.SESSION_NAME
    assert session2 == current_session


def test_no_session_in_objects_list(session3):
    with pytest.warns(RuntimeWarning):
        session3.setup()


def test_load_script(session2, session4, capsys):
    env_dict = dict()
    session2.setup(env_dict)
    assert env_dict.get("_hidden_func") is None
    assert env_dict.get("visible_func") is not None

    env_dict = dict()
    session4.setup(env_dict)
    assert env_dict["load_script"] is not None
    load_script = env_dict["load_script"]
    load_script("script3", "test_session5")
    assert env_dict.get("test_func") is not None

    assert env_dict.get("test1") is not None
    assert env_dict["test_session5"].env_dict == {}

    from bliss.session.test_session5 import script3

    assert script3.test_func

    env_dict = dict()
    session4.setup(env_dict)
    assert "RuntimeError" in capsys.readouterr()[1]


def test_load_script_namespace(session4):
    env_dict = dict()
    session4.setup(env_dict)
    assert env_dict["a"] == 2


def test_user_script(session4, capsys):
    env_dict = dict()
    session4.setup(env_dict)

    user_script_load = env_dict.get("user_script_load")
    user_script_run = env_dict.get("user_script_run")
    user_script_list = env_dict.get("user_script_list")
    user_script_homedir = env_dict.get("user_script_homedir")
    assert user_script_load is not None
    assert user_script_run is not None
    assert user_script_list is not None
    assert user_script_homedir is not None

    assert user_script_homedir() is None
    with pytest.raises(RuntimeError):
        user_script_list()

    from tests.conftest import BEACON_DB_PATH

    user_script_homedir(BEACON_DB_PATH)
    assert user_script_homedir() == BEACON_DB_PATH
    capsys.readouterr()
    user_script_list()
    assert "sessions/subdir/scripts/simple_script.py" in capsys.readouterr()[0]

    user_script_run("sessions/scripts/script3")
    assert "toto" not in session4.env_dict
    user_script_load("sessions/scripts/script3", export_global=True)
    assert "toto" in session4.env_dict

    ns = user_script_load("sessions/subdir/scripts/simple_script")
    assert list(ns.__dict__) == ["ascan", "time", "test1", "a"]


def test_prdef(session2, capsys):
    visible_func_code = "\ndef visible_func():\n    pass\n\n"
    env_dict = dict()
    session2.setup(env_dict)
    capsys.readouterr()
    from bliss.session.test_session2 import script1

    assert callable(env_dict.get("prdef"))
    env_dict["prdef"](script1.visible_func)
    output = capsys.readouterr()[0]
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    assert ansi_escape.sub("", output).endswith(visible_func_code)

    env_dict["prdef"](scans.cen)
    output = ansi_escape.sub("", capsys.readouterr()[0])
    assert "@_multimotors\ndef cen(" in output


def test_session_env_dict(session):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_session",
        expert_error_report=True,
    )
    assert id(cli.get_globals()) == id(session.env_dict)


def test_failing_session_globals(failing_session):
    inp = create_pipe_input()
    _ = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="failing_setup_session",
        expert_error_report=True,
    )
    assert "SCANS" in failing_session.env_dict
    assert "SCAN_SAVING" in failing_session.env_dict
