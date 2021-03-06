# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import os
import pytest
from treelib import Tree

from bliss import current_session
from bliss.shell.cli import repl
from bliss import setup_globals
from bliss.common import scans, session
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

    with pytest.raises(RuntimeError):
        load_script("doesnotexist")


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
    assert callable(user_script_load)
    assert callable(user_script_run)
    assert callable(user_script_list)
    assert callable(user_script_homedir)

    assert user_script_homedir() is None
    with pytest.raises(RuntimeError):
        user_script_list()

    from tests.conftest import BEACON_DB_PATH

    # test user_script_homedir and user_script_list
    user_script_homedir(BEACON_DB_PATH)
    assert user_script_homedir() == BEACON_DB_PATH
    capsys.readouterr()
    user_script_list()
    assert "sessions/subdir/scripts/simple_script.py" in capsys.readouterr()[0]

    # test that user_script_run does not export things
    user_script_run("sessions/scripts/script3")
    assert "toto" not in session4.env_dict
    assert "user" not in session4.env_dict
    # test that user_script_load can export to global env dict
    user_script_load("sessions/scripts/script3", export_global=True)
    assert "toto" in session4.env_dict

    # test that user_script_load can return a namespace
    expected_symbols = ["ascan", "time", "test1", "a"]
    ns = user_script_load("sessions/subdir/scripts/simple_script", export_global=False)
    assert list(ns._fields) == expected_symbols

    session4.env_dict["user"] = 42
    user_script_load("sessions/subdir/scripts/simple_script")

    # test that user_script_load can export to "user" namespace
    assert list(session4.env_dict["user"]._fields) == expected_symbols

    session4.env_dict["user_ns"] = session4.env_dict["user"]
    session4.env_dict["user_ns"].a == 0
    user_script_load("sessions/subdir/scripts/simple_script", export_global="user_ns")
    user_script_load("sessions/scripts/script3", export_global="user_ns")
    # test that user_script_load can merge to existing namespace
    assert session4.env_dict["user_ns"].a == 42
    assert session4.env_dict["user_ns"].toto == 42


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

    env_dict["prdef"](scans.ascan)
    output = ansi_escape.sub("", capsys.readouterr()[0])
    assert "@typeguard.typechecked\ndef ascan(" in output

    # test prdef cache - #1900
    script_file = "/tmp/script.py"

    try:
        with open(script_file, "w") as f:
            f.write(visible_func_code)

        user_script_load = env_dict.get("user_script_load")
        assert callable(user_script_load)
        user_script_load(script_file)
        env_dict["prdef"](env_dict["user"].visible_func)

        new_visible_func_code = '\ndef visible_func():\n    print("hello)\n\n'

        with open(script_file, "w") as f:
            f.write(new_visible_func_code)

        with pytest.raises(SyntaxError):
            user_script_load(script_file)
        env_dict["prdef"](env_dict["user"].visible_func)
        output = ansi_escape.sub("", capsys.readouterr()[0])
        assert "hello" not in output

    finally:
        os.unlink(script_file)


def test_session_env_dict(session):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_session",
        expert_error_report=True,
    )
    assert id(cli.get_globals().wrapped_dict) == id(session.env_dict)


def test_session_env_dict_no_protection_library_mode(session):
    env_dict = session.env_dict
    assert "roby" in env_dict
    env_dict["roby"] = 17


def test_session_env_dict_conf_obj_protection(session):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_session",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()

    with pytest.raises(RuntimeError):
        prot_env_dict["roby"] = 17


def test_session_env_dict_alias_protection(beacon):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_alias",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()

    with pytest.raises(RuntimeError):
        prot_env_dict["robyy"] = 17


def test_session_env_dict_protection_imports_globals(beacon):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_alias",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()

    with pytest.raises(RuntimeError):
        prot_env_dict["ascan"] = 17

    try:
        from bliss.common.scans import ascan

        prot_env_dict["ascan"] = ascan
    except RuntimeError:
        pytest.fail("Items protection should not reject imports")

    with pytest.raises(RuntimeError):
        prot_env_dict["SCAN_DISPLAY"] = 17


def test_session_env_dict_protection_inherited(session2):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_session2",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()

    with pytest.raises(RuntimeError):
        prot_env_dict["roby"] = 17


def test_session_env_dict_protection_on_the_fly(alias_session):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_alias",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()
    prot_env_dict["unprotect"]("roby")
    prot_env_dict["roby"] = 17
    assert prot_env_dict["roby"] == 17
    prot_env_dict["protect"]("roby")
    assert prot_env_dict["roby"] == 17
    with pytest.raises(RuntimeError):
        prot_env_dict["roby"] = 18

    # config.get should always work, even on protected keys
    prot_env_dict["config"].get("roby")
    assert prot_env_dict["roby"].name == "roby"


def test_session_env_dict_protection_nonexisting_keys(session2):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_session2",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()

    assert "var1" in prot_env_dict._protected_keys
    assert "var3" not in prot_env_dict._protected_keys

    with pytest.raises(AssertionError):
        prot_env_dict["protect"]("nothing")

    with pytest.raises(AssertionError):
        prot_env_dict["unprotect"]("nothing")

    # check that session env dict is in sync
    prot_env_dict["var3"] = 3
    lib_env_dict = session2.env_dict
    assert lib_env_dict["var3"] == 3
    lib_env_dict["protect"]("var3")
    with pytest.raises(RuntimeError):
        prot_env_dict["var3"] = 4
    lib_env_dict["unprotect"]("var3")
    prot_env_dict["var3"] = 4


def test_session_env_dict_setup_protection(session2):
    inp = create_pipe_input()
    cli = repl.cli(
        input=inp,
        output=DummyOutput(),
        session_name="test_session2",
        expert_error_report=True,
    )
    prot_env_dict = cli.get_globals()

    with pytest.raises(RuntimeError):
        prot_env_dict["toto"] = 18

    with pytest.raises(RuntimeError):
        prot_env_dict["var1"] = 2


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


def test_temp_export_axes(beacon):
    default_session = session.DefaultSession()
    env = dict()
    default_session.setup(env_dict=env)

    def check_axes(*axis_names):
        axes = list()
        with default_session.temporary_config as cfg:
            for name in axis_names:
                axes.append(cfg.get(name))
            # check that env dict contains axes
            assert set(axis_names).intersection(env) == set(axis_names)
        assert set(axis_names).intersection(env) == set()

    check_axes("roby", "robz")


def test_issue_1924(beacon):
    s = beacon.get("test_session")
    s.setup()
    assert s.name == "test_session"
    assert s.scan_saving.session == "test_session"
    test_session_ss_info = s.scan_saving.__info__()
    s2 = beacon.get("flint")  # another session, can be any
    s2.setup()
    assert s2.name == "flint"
    assert s2.scan_saving.session == "flint"
    assert s2.scan_saving.__info__() != test_session_ss_info
    s.close()
    s2.close()


def test_issue_2218(beacon):
    # No data policy allowed in the default session
    scan_saving_cfg = beacon.root["scan_saving"]
    scan_saving_cfg["class"] = "ESRFScanSaving"
    default_session = session.DefaultSession()
    default_session.setup()
    assert default_session.scan_saving.__class__.__name__ != "ESRFScanSaving"
    default_session.enable_esrf_data_policy()
    assert default_session.scan_saving.__class__.__name__ != "ESRFScanSaving"


def test_session_exit_on_timeout(beacon):
    """
    Test robustness of a session setup to many exceptions.
    NB: initial bug was: session exits on timeout.
    """
    bsession = beacon.get("test_exceptions_session")
    assert not bsession.setup()
    assert bsession.name == "test_exceptions_session"
    bsession.close()
