# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import sys

from prompt_toolkit.input.defaults import create_pipe_input
from bliss.shell.cli.repl import BlissRepl
from prompt_toolkit.output import DummyOutput
from bliss.shell.cli.repl import _set_pt_event_loop


def _feed_cli_with_input(text, check_line_ending=True):
    _set_pt_event_loop()
    """
    Create a Prompt, feed it with the given user input and return the CLI
    object.

    Inspired by python-prompt-toolkit/tests/test_cli.py
    """
    # If the given text doesn't end with a newline, the interface won't finish.
    if check_line_ending:
        assert text.endswith("\r")

    inp = create_pipe_input()

    try:

        br = BlissRepl(input=inp, output=DummyOutput(), session="test_session")
        inp.send_text(text)
        result = br.app.run()
        return result, br.app, br

    finally:
        inp.close()


def test_shell_exit(clean_gevent):
    clean_gevent["end-check"] = False
    try:
        _feed_cli_with_input(chr(0x4) + "y", check_line_ending=False)
    except EOFError:
        assert True


def test_shell_exit2(clean_gevent):
    clean_gevent["end-check"] = False
    try:
        _feed_cli_with_input(chr(0x4) + "\r", check_line_ending=False)
    except EOFError:
        assert True


def test_shell_noexit(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, br = _feed_cli_with_input(
        chr(0x4) + "nprint 1 2\r", check_line_ending=True
    )
    assert result == "print(1,2)"


def test_shell_ctrl_r(clean_gevent):
    clean_gevent["end-check"] = False

    result, cli, br = _feed_cli_with_input(
        chr(0x12) + "bla blub\r\r", check_line_ending=True
    )
    assert result == ""

    result, cli, br = _feed_cli_with_input(
        "from bliss import setup_globals\rfrom subprocess import Popen\r"
        + chr(0x12)
        + "from bl\r\r",
        check_line_ending=True,
    )
    assert result == "from bliss import setup_globals"


def test_shell_prompt_number(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, br = _feed_cli_with_input("print 1\r")
    num1 = br.bliss_prompt.python_input.current_statement_index
    br._execute(result)
    num2 = br.bliss_prompt.python_input.current_statement_index
    assert num2 == num1 + 1
    br._execute(result)
    num3 = br.bliss_prompt.python_input.current_statement_index
    assert num3 == num1 + 2


def test_shell_comma_backets(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("print 1 2\r")
    assert result == "print(1,2)"


def test_shell_string_input(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("a='to to'\r")
    assert result == "a='to to'"


def test_shell_string_parameter(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("print 'bla bla'\r")
    assert result == "print('bla bla')"


def test_shell_function_without_parameter(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("print \r")
    assert result == "print()"


def test_shell_function_with_return_only(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("\r")
    assert result == ""


def test_shell_semicolon(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("print 1 2;print 1\r")
    assert result == "print(1,2);print(1)"
