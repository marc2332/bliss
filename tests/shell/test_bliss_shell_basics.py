# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
import sys
import logging
import contextlib
from unittest import mock
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from bliss.common.logtools import Elogbook
from bliss.shell.standard import elog_add
import bliss.shell.cli
import pytest
import gevent

from bliss.shell.cli.repl import (
    BlissRepl,
    PromptToolkitOutputWrapper,
    install_excepthook,
)


class DummyTestOutput(DummyOutput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = []

    def write(self, text):
        self._data.append(text)

    def flush(self):
        print("".join(self._data))
        self._data = []


def _feed_cli_with_input(
    text, check_line_ending=True, local_locals=None, local_globals=None, timeout=10
):
    """
    Create a Prompt, feed it with the given user input and return the CLI
    object.

    Inspired by python-prompt-toolkit/tests/test_cli.py
    """
    # If the given text doesn't end with a newline, the interface won't finish.
    if check_line_ending:
        assert text.endswith("\r")

    inp = create_pipe_input()

    if local_locals is None:
        local_locals = {}

    def mylocals():
        return local_locals

    if local_globals:

        def myglobals():
            return local_globals

    else:
        myglobals = None

    try:
        inp.send_text(text)
        br = BlissRepl(
            input=inp,
            output=DummyTestOutput(),
            session="test_session",
            get_locals=mylocals,
            get_globals=myglobals,
        )

        def exit_after_timeout(app, timeout):
            gevent.sleep(timeout)
            app.exit()

        br.app.output = PromptToolkitOutputWrapper(br.app.output)
        gtimeout = gevent.spawn(exit_after_timeout, br.app, timeout)
        result = br.app.run()
        return result, br.app, br

    finally:
        gtimeout.kill()
        BlissRepl.instance = None  # BlissRepl is a Singleton
        inp.close()


def run_repl_once(bliss_repl, text):
    bliss_repl.app.input.send_text(text)
    try:
        res = bliss_repl.eval(bliss_repl.app.run())
    except KeyboardInterrupt as e:  # KeyboardInterrupt doesn't inherit from Exception.
        raise
    except SystemExit:
        return
    except BaseException as e:
        bliss_repl._handle_exception(e)
    else:
        if res is not None:
            bliss_repl.show_result(res)


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
    from bliss.scanning.scan_saving import ScanSaving

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
        BlissRepl.instance = None  # BlissRepl is a Singleton
        inp.close()


def test_protected_against_trailing_whitespaces():
    """ Check that the number of spaces (N) after a command doesn't  make the command to be repeated N-1 times """

    def f():
        print("Om Mani Padme Hum")

    result, cli, br = _feed_cli_with_input(f"f() {' '*5}\r", local_locals={"f": f})

    output = cli.output
    br.eval(result)

    assert output[-1].strip() == "Om Mani Padme Hum"


def test_info_dunder():
    class A:
        def __repr__(self):
            return "repr-string"

        def __str__(self):
            return "str-string"

        def __info__(self):
            return "info-string"

        def titi(self):
            return "titi-method"

    class B:
        def __repr__(self):
            return "repr-string"

    class C:
        pass

    # '__info__()' method called at object call.
    with bliss_repl({"A": A(), "B": B(), "C": C()}) as bliss_repl_ctx:
        inp, br = bliss_repl_ctx
        run_repl_once(br, "A\r")
        assert "info-string" in br.app.output[-1]

        run_repl_once(br, "[A]\r")
        assert "[repr-string]" in br.app.output[-1]

        # 2 parenthesis added to method if not present
        run_repl_once(br, "A.titi\r")
        assert "titi-method" in br.app.output[-1]

        # Closing parenthesis added if only opening one is present.
        run_repl_once(br, "A.titi(\r")
        assert "titi-method" in br.app.output[-1]

        # Ok if finishing by a closing parenthesis.
        run_repl_once(br, "A.titi()\r")
        assert "titi-method" in br.app.output[-1]

        # '__repr__()' used if no '__info__()' method is defined.
        run_repl_once(br, "B\r")
        assert "repr-string" in br.app.output[-1]

        # Default behaviour for object without specific method.
        run_repl_once(br, "C\r")
        assert "C object at " in br.app.output[-1]

    bliss.shell.cli.typing_helper_active = False
    try:
        with bliss_repl({"A": A, "B": B, "A.titi": A.titi}) as bliss_repl_ctx:
            inp, br = bliss_repl_ctx
            output = br.app.output
            run_repl_once(br, "A\r")
            assert (
                "<class 'test_bliss_shell_basics.test_info_dunder.<locals>.A'>\r\n\n"
                == output[-1]
            )
    finally:
        bliss.shell.cli.typing_helper_active = True


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


def test_deprecation_warning(beacon, capfd, log_context):
    def test_deprecated():
        print("bla")
        from bliss.common.deprecation import deprecated_warning

        deprecated_warning(
            kind="function",
            name="ct",
            replacement="sct",
            reason="`ct` does no longer allow to save data",
            since_version="1.5.0",
            skip_backtrace_count=5,
            only_once=False,
        )

    with bliss_repl({"func": test_deprecated}) as bliss_repl_ctx:
        inp, br = bliss_repl_ctx
        inp.send_text("func()\r")
        result = br.app.run()
        br.eval(result)
        captured = capfd.readouterr()

    out = _repl_out_to_string(captured.out)
    err = _repl_out_to_string(captured.err)
    assert "bla" in out
    assert "Function ct is deprecated since" in err


def test_captured_output():
    def f(num):
        print(num + 1)
        return num + 2

    with bliss_repl({"f": f}) as bliss_repl_ctx:
        inp, br = bliss_repl_ctx
        output = br.app.output

        run_repl_once(br, "f(1)\r")

        captured = output[-1]
        assert "2" in captured
        assert "3" in captured
        captured = output[1]
        assert "2" in captured
        assert "3" in captured
        with pytest.raises(IndexError):
            output[2]

        run_repl_once(br, "f(3)\r")

        captured = output[-1]
        assert "4" in captured
        assert "5" in captured
        captured = output[1]
        assert "2" in captured
        assert "3" in captured
        captured = output[2]
        assert "4" in captured
        assert "5" in captured
        with pytest.raises(IndexError):
            output[-10]


def test_elogbook_cmd_log_and_elog_add(shell_excepthook):
    logger = logging.getLogger()

    def f(num):
        print(num + 1)
        logger.info("my info")
        logger.error("my error")
        return num + 2

    with bliss_repl({"f": f, "elog_add": elog_add}) as bliss_repl_ctx:
        inp, br = bliss_repl_ctx

        # calling when no command has been issued yet should not raise exception
        elog_add()

        with mock.patch.object(
            Elogbook, "command", return_value=None
        ) as mock_elogbook_command:
            run_repl_once(br, "f(1)\r")

            output = br.app.output
            captured = output[-1]

        mock_elogbook_command.assert_called_once_with("f(1)")
        assert captured == "2\n3\r\n\n"

        with mock.patch.object(
            Elogbook, "comment", return_value=None
        ) as mock_elogbook_comment:
            run_repl_once(br, "elog_add()\r")

        mock_elogbook_comment.assert_called_once_with(captured)

        with mock.patch.object(
            Elogbook, "error", return_value=None
        ) as mock_elogbook_error:
            run_repl_once(br, "1/0\r")

        mock_elogbook_error.assert_called_once_with(
            "ZeroDivisionError: division by zero"
        )

        with mock.patch.object(
            Elogbook, "comment", return_value=None
        ) as mock_elogbook_comment:
            run_repl_once(br, "elog_add()\r")

        # last output is an exception => elog_add() should return an empty string,
        # as there is no "output" for the logbook in the context of elog_add
        # since there was an exception
        mock_elogbook_comment.assert_called_once_with("")


def test_getattribute_evaluation():
    n = None

    class A:
        def __init__(self):
            global n
            n = 0

        def __getattribute__(self, value):
            global n

            if n < 1:
                n += 1
                raise RuntimeError
            return 0

    a = A()

    with gevent.timeout.Timeout(3):
        result, cli, _ = _feed_cli_with_input("a.foo()\r", local_globals={"a": a})


@pytest.fixture
def shell_excepthook():
    orig_excepthook = sys.excepthook
    try:
        install_excepthook()
        yield
    finally:
        sys.excepthook = orig_excepthook


def test_excepthook(shell_excepthook, default_session):
    print_output = []

    def test_print(*msg, **kw):
        print_output.append("\n".join(msg))

    logging.getLogger("exceptions").setLevel(
        1000
    )  # this is to silent exception logging via logger (which also calls 'print')

    with mock.patch("builtins.print", test_print):
        try:
            raise RuntimeError("excepthook test")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())

    assert (
        "".join(print_output)
        == "!!! === RuntimeError: excepthook test === !!! ( for more details type cmd 'last_error' )"
    )
