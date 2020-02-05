# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import contextlib
from prompt_toolkit.input.defaults import create_pipe_input
from bliss.shell.cli.repl import BlissRepl
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.eventloop import get_event_loop


def _feed_cli_with_input(text, check_line_ending=True, local_locals={}):
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
        get_event_loop().close()


def test_shell_exit():
    try:
        _feed_cli_with_input(chr(0x4) + "y", check_line_ending=False)
    except EOFError:
        assert True


def test_shell_exit2():
    try:
        _feed_cli_with_input(chr(0x4) + "\r", check_line_ending=False)
    except EOFError:
        assert True


def test_shell_noexit():
    result, cli, br = _feed_cli_with_input(
        chr(0x4) + "nprint 1 2\r", check_line_ending=True
    )
    assert result == "print(1,2)"


def test_shell_ctrl_r():

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


def test_shell_prompt_number():
    result, cli, br = _feed_cli_with_input("print 1\r")
    num1 = br.bliss_prompt.python_input.current_statement_index
    br._execute(result)
    num2 = br.bliss_prompt.python_input.current_statement_index
    assert num2 == num1 + 1
    br._execute(result)
    num3 = br.bliss_prompt.python_input.current_statement_index
    assert num3 == num1 + 2


def test_shell_comma_backets():
    result, cli, _ = _feed_cli_with_input("print 1 2\r")
    assert result == "print(1,2)"


def test_shell_string_input():
    result, cli, _ = _feed_cli_with_input("a='to to'\r")
    assert result == "a='to to'"


def test_shell_string_parameter():
    result, cli, _ = _feed_cli_with_input("print 'bla bla'\r")
    assert result == "print('bla bla')"


def test_shell_function_without_parameter():
    result, cli, _ = _feed_cli_with_input("print\r")
    assert result == "print"

    def f():
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f()"


def test_shell_function_with_return_only():
    result, cli, _ = _feed_cli_with_input("\r")
    assert result == ""


def test_shell_callable_with_args():
    result, cli, _ = _feed_cli_with_input("sum\r")
    assert result == "sum"

    def f(arg):
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f"


def test_shell_callable_with_kwargs_only():
    result, cli, _ = _feed_cli_with_input("property\r")
    assert result == "property()"

    def f(arg="bla"):
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f()"


def test_shell_callable_with_args_and_kwargs():
    result, cli, _ = _feed_cli_with_input("compile\r")
    assert result == "compile"

    def f(arg, kwarg="bla"):
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f"


def test_shell_list():
    result, cli, _ = _feed_cli_with_input("list\r")
    assert result == "list"

    l = list()
    result, cli, _ = _feed_cli_with_input("l\r", local_locals={"l": l})
    assert result == "l"


def test_shell_ScanSaving(beacon):
    from bliss.scanning.scan import ScanSaving

    s = ScanSaving()

    result, cli, _ = _feed_cli_with_input("s\r", local_locals={"s": s})
    assert result == "s"


def test_shell_func():
    def f():
        pass

    result, cli, _ = _feed_cli_with_input("f\r", local_locals={"f": f})
    assert result == "f()"


def test_shell_semicolon():
    result, cli, _ = _feed_cli_with_input("print 1 2;print 1\r")
    assert result == "print(1,2);print(1)"
    result, cli, _ = _feed_cli_with_input("print 1 2;print 1;print 23\r")
    assert result == "print(1,2);print(1);print(23)"


def test_shell_comma_outside_callable_assignment():
    result, cli, _ = _feed_cli_with_input("a=True \r")
    assert result == "a=True"


def test_shell_comma_outside_callable_bool():
    result, cli, _ = _feed_cli_with_input("True \r")
    assert result == "True"


def test_shell_comma_outside_callable_string():
    result, cli, _ = _feed_cli_with_input("'bla' \r")
    assert result == "'bla'"


def test_shell_comma_outside_callable_number():
    result, cli, _ = _feed_cli_with_input("1.1 + 1  \r")
    assert result == "1.1 + 1"


def test_shell_comma_after_comma():
    result, cli, _ = _feed_cli_with_input("1, \r")
    assert result == "1,"


@contextlib.contextmanager
def bliss_repl(locals_dict):
    inp = create_pipe_input()

    def mylocals():
        return locals_dict

    try:
        br = BlissRepl(
            input=inp, output=DummyOutput(), session="test_session", get_locals=mylocals
        )
        yield inp, br
    finally:
        inp.close()
        get_event_loop().close()


def test_info_dunder(capfd):
    class A(object):
        def __repr__(self):
            return "repr-string"

        def __str__(self):
            return "str-string"

        def __info__(self):
            return "info-string"

        def titi(self):
            return "titi-method"

    class B(object):
        def __repr__(self):
            return "repr-string"

    class C(object):
        pass

    # '__info__()' method called at object call.
    result, cli, br = _feed_cli_with_input("A\r", local_locals={"A": A(), "B": B()})
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "info-string" in out

    result, cli, br = _feed_cli_with_input("[A]\r", local_locals={"A": A(), "B": B()})
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "[repr-string]" in out

    # 2 parenthesis added to method if not present
    result, cli, br = _feed_cli_with_input(
        "A.titi\r", local_locals={"A": A(), "B": B()}
    )
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "titi-method" in out

    # Closing parenthesis added if only opening one is present.
    result, cli, br = _feed_cli_with_input(
        "A.titi(\r", local_locals={"A": A(), "B": B()}
    )
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "titi-method" in out

    # Ok if finishing by a closing parenthesis.
    result, cli, br = _feed_cli_with_input(
        "A.titi()\r", local_locals={"A": A(), "B": B()}
    )
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "titi-method" in out

    # '__repr__()' used if no '__info__()' method is defined.
    result, cli, br = _feed_cli_with_input("B\r", local_locals={"A": A(), "B": B()})
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "repr-string" in out

    # Default behaviour for object without specific method.
    result, cli, br = _feed_cli_with_input(
        "C\r", local_locals={"A": A(), "B": B(), "C": C()}
    )
    br._execute(result)
    captured = capfd.readouterr()
    out = _repl_out_to_string(captured.out)
    assert "C object at " in out

    ###bypass typing helper ... equivalent of ... [Space][left Arrow]A[return], "B": B, "A.titi": A.titi}, "B": B, "A.titi": A.titi}
    with bliss_repl({"A": A, "B": B, "A.titi": A.titi}) as bliss_repl_ctx:
        inp, br = bliss_repl_ctx
        inp.send_text("")
        br.default_buffer.insert_text("A ")
        inp.send_text("\r")
        result = br.app.run()
        assert result == "A ()"
        br._execute(result)
        captured = capfd.readouterr()
        out = _repl_out_to_string(captured.out)
        # assert "<locals>.A" in out
        assert "  Out [1]: info-string\r\n\r\n" == out

    with bliss_repl({"A": A, "B": B, "A.titi": A.titi}) as bliss_repl_ctx:
        inp, br = bliss_repl_ctx
        inp.send_text("")
        br.default_buffer.insert_text("B ")
        inp.send_text("\r")
        result = br.app.run()
        assert result == "B ()"
        br._execute(result)
        captured = capfd.readouterr()
        out = _repl_out_to_string(captured.out)

        # assert "<locals>.B" in out
        assert "  Out [1]: repr-string\r\n\r\n" == out


def test_shell_dict_list_not_callable():
    result, cli, _ = _feed_cli_with_input("d \r", local_locals={"d": dict()})
    assert result == "d"


def test_property_evaluation():
    class Bla:
        def __init__(self):
            self.i = 0

        @property
        def test(self):
            self.i += 1
            return self.i

    b = Bla()

    result, cli, _ = _feed_cli_with_input("b.test     \r", local_locals={"b": b})
    assert b.test == 1
    result, cli, _ = _feed_cli_with_input("b.test;print 1\r", local_locals={"b": b})
    result, cli, _ = _feed_cli_with_input("b.test;print 1\r", local_locals={"b": b})
    result, cli, _ = _feed_cli_with_input("b.test;print 1\r", local_locals={"b": b})
    assert b.test == 2


def test_func_no_args():
    f = lambda: None
    result, cli, _ = _feed_cli_with_input("f \r", local_locals={"f": f})
    assert result == "f()"


def _repl_out_to_string(out):
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", out)


def test_nested_property_evaluation():
    class A:
        def __init__(self):
            self.count = 0

        @property
        def foo(self):
            self.count += 1
            return self.count

    class B:
        def __init__(self):
            self.a = A()

        @property
        def bar(self):
            return self.a

    b = B()

    result, cli, _ = _feed_cli_with_input("b.bar.foo\r", local_locals={"b": b})
    result, cli, _ = _feed_cli_with_input("b.bar.foo\r", local_locals={"b": b})
    assert b.bar.foo == 1
