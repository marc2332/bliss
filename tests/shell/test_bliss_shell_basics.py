# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest

from prompt_toolkit.input.defaults import create_pipe_input
from bliss.shell.cli.repl import BlissRepl
from prompt_toolkit.output import DummyOutput


def _feed_cli_with_input(text, check_line_ending=True):
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

        br = BlissRepl(
            input=inp, output=DummyOutput(), scan_listener=None, session="test_session"
        )
        inp.send_text(text)
        result = br.app.run()

        return result, br.app

    finally:
        inp.close()


def test_shell_comma_backets():
    result, cli = _feed_cli_with_input("print 1 2\r")
    assert result == "print(1,2)"


def test_shell_string_input():
    result, cli = _feed_cli_with_input("a='to to'\r")
    assert result == "a='to to'"


def test_shell_string_parameter():
    result, cli = _feed_cli_with_input("print 'bla bla'\r")
    assert result == "print('bla bla')"


def test_shell_function_without_parameter():
    result, cli = _feed_cli_with_input("print \r")
    assert result == "print()"


## missing test for semicolon which is not working in this test settingpri
# def test_shell_semicolon():
#    result, cli = _feed_cli_with_input("print 1 2 ;print 1\r")
#    assert result == "print(1,2);print(1)"
