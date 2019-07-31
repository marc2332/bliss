# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import sys
import re

from prompt_toolkit.input.defaults import create_pipe_input
from bliss.shell.cli.repl import BlissRepl
from prompt_toolkit.output import DummyOutput
from bliss.shell.cli.repl import _set_pt_event_loop


def _feed_cli_with_input(text, check_line_ending=True, local_locals={}):
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

    def mylocals():
        return local_locals

    try:

        br = BlissRepl(
            input=inp, output=DummyOutput(), session="test_session", get_locals=mylocals
        )
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
    result, cli, _ = _feed_cli_with_input("print\r")
    assert result == "print"

    def f():
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f()"


def test_shell_function_with_return_only(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("\r")
    assert result == ""


def test_shell_callable_with_args(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("sum\r")
    assert result == "sum"

    def f(arg):
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f"


def test_shell_callable_with_kwargs_only(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("property\r")
    assert result == "property()"

    def f(arg="bla"):
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f()"


def test_shell_callable_with_args_and_kwargs(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("compile\r")
    assert result == "compile"

    def f(arg, kwarg="bla"):
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f"


def test_shell_list(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("list\r")
    assert result == "list"

    l = list()
    result, cli, _ = _feed_cli_with_input("l\r", local_locals={"l": l})
    assert result == "l"


def test_shell_ScanSaving(clean_gevent):
    clean_gevent["end-check"] = False

    from bliss.scanning.scan import ScanSaving

    s = ScanSaving()

    result, cli, _ = _feed_cli_with_input("s\r", local_locals={"s": s})
    assert result == "s"


def test_shell_func(clean_gevent):
    clean_gevent["end-check"] = False

    def f():
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f()"


def test_shell_semicolon(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("print 1 2;print 1\r")
    assert result == "print(1,2);print(1)"


def test_shell_comma_outside_callable_assignment(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("a=True \r")
    assert result == "a=True"


def test_shell_comma_outside_callable_bool(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("True \r")
    assert result == "True"


def test_shell_comma_outside_callable_string(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("'bla' \r")
    assert result == "'bla'"


def test_shell_comma_outside_callable_number(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("1.1 + 1  \r")
    assert result == "1.1 + 1"


def test_shell_comma_after_comma(clean_gevent):
    clean_gevent["end-check"] = False
    result, cli, _ = _feed_cli_with_input("1, \r")
    assert result == "1,"


def test_info_dunder(clean_gevent, capfd):
    clean_gevent["end-check"] = False

    class A(object):
        def __repr__(self):
            return "repr"

        def __str__(self):
            return "str"

        def __info__(self):
            return "info"

    class B(object):
        def __repr__(self):
            return "repr"

    class C(object):
        pass

    result, cli, br = _feed_cli_with_input("A\r", local_locals={"A": A(), "B": B()})
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "info" in out

    result, cli, br = _feed_cli_with_input("B\r", local_locals={"A": A(), "B": B()})
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "repr" in out

    result, cli, br = _feed_cli_with_input(
        "C\r", local_locals={"A": A(), "B": B(), "C": C()}
    )
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "C object at " in out

    ###bypass typing helper ... equivalent of ... [Space][left Arrow]A[return]
    inp = create_pipe_input()

    def mylocals():
        return {"A": A, "B": B}

    try:

        br = BlissRepl(
            input=inp, output=DummyOutput(), session="test_session", get_locals=mylocals
        )
        inp.send_text("")
        br.default_buffer.insert_text("A ")
        inp.send_text("\r")
        result = br.app.run()
        assert result == "A"
        br._execute(result)
        captured = capfd.readouterr()
        out = _repl_out_to_string(captured.out)
        assert "<locals>.A" in out

        br = BlissRepl(
            input=inp, output=DummyOutput(), session="test_session", get_locals=mylocals
        )
        inp.send_text("")
        br.default_buffer.insert_text("B ")
        inp.send_text("\r")
        result = br.app.run()
        assert result == "B"
        br._execute(result)
        captured = capfd.readouterr()
        out = _repl_out_to_string(captured.out)

        assert "<locals>.B" in out

    finally:
        inp.close()


def _repl_out_to_string(out):
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", out)
