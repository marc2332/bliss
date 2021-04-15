# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Test for the typing helper integration in ptpython.
"""

import gevent
import contextlib
import greenlet
import asyncio

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput

from bliss.shell.cli.repl import BlissRepl


class DummyTestOutput(DummyOutput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = []

    def write(self, text):
        self._data.append(text)

    def flush(self):
        print("".join(self._data))
        self._data = []


def _run_incomplete(cmd_input, local_locals, stop_condition=None):
    """
    Run an incomplete command in the BLISS shell.

    FIXME: This function should be reworked to get ride of `Timeout`. The
    processing can change a lot, depending of the load of the machine , and
    because jedi uses a cache.

    To test it in CI conditions, you can use `rm -rf ~/.cache/jedi`.

    Argument:
        - cmd_input: Command to execute
        - local_locals: Environment to use for the auto-completion.
        - stop_condition: Termination condition checked at application rendering
    """
    assert BlissRepl.instance is None

    inp = create_pipe_input()

    def mylocals():
        return local_locals

    br = BlissRepl(
        input=inp, output=DummyTestOutput(), session="test_session", get_locals=mylocals
    )
    inp.send_text(cmd_input)

    class RunAborted(BaseException):
        pass

    greenlet_current = greenlet.getcurrent()

    def abort_app():
        """Abort the app.run call"""
        nonlocal greenlet_current
        greenlet_current.throw(RunAborted)

    if stop_condition is None:
        # There is no end condition cause no result is expected
        # So reduce the timeout, cause we could wait forever
        timeout = 10
    else:
        timeout = 3

    def app_exit():
        nonlocal br
        try:
            br.app.exit()
        except Exception:
            pass

    def app_exit_after_timeout():
        nonlocal timeout
        gevent.sleep(timeout)
        app_exit()

    @contextlib.contextmanager
    def hooked_render():
        """Context manager to add a hook in the prompt_toolkit renderer.

        The hook test a condition to allow to abort the application execution.
        """
        from prompt_toolkit.renderer import Renderer

        old_function = Renderer.render

        def new_function(self, *args, **kwargs):
            nonlocal br
            old_function(self, *args, **kwargs)
            if stop_condition is not None and stop_condition(br):
                app_exit()

        Renderer.render = new_function
        try:
            yield
        finally:
            Renderer.render = old_function

    try:
        qtimeout = gevent.spawn(app_exit_after_timeout)
        run_async = br.app.run_async(set_exception_handler=False)
        with hooked_render():
            asyncio.run(run_async)
    finally:
        inp.close()
        qtimeout.kill()
        BlissRepl.instance = None

    return br


def _default_buffer_from_incomplete_run(command, env_dict):
    data = 0

    def on_second_render(br):
        nonlocal data
        if data >= 1:
            return True
        data = data + 1
        return False

    br = _run_incomplete(command, env_dict, stop_condition=on_second_render)
    return br.default_buffer.text


@contextlib.contextmanager
def session_env_dict(beacon, session_name):
    try:
        env_dict = dict()
        session = beacon.get(session_name)
        session.setup(env_dict)
        yield env_dict
    finally:
        session.close()


def test_shell_comma_object():
    text = _default_buffer_from_incomplete_run("print self \r", {})
    assert text == "print(self,\n"


def test_shell_comma_after_comma_inside_callable():
    text = _default_buffer_from_incomplete_run("print(1, ", {})
    assert text == "print(1, "


def test_shell_comma_int():
    text = _default_buffer_from_incomplete_run("print 1 ", {})
    assert text == "print(1,"


def test_shell_comma_float():
    text = _default_buffer_from_incomplete_run("print 1.1 ", {})
    assert text == "print(1.1,"


def test_shell_comma_bool():
    text = _default_buffer_from_incomplete_run("print False ", {})
    assert text == "print(False,"


def test_shell_comma_string():
    text = _default_buffer_from_incomplete_run("print 'bla' ", {})
    assert text == "print('bla',"


def test_shell_comma_kwarg():
    text = _default_buffer_from_incomplete_run("print run=True ", {})
    assert text == "print(run=True,"


def test_shell_custom_function_kwarg():
    def f(**kwargs):
        return True

    text = _default_buffer_from_incomplete_run("f ", {"f": f})
    assert text == "f("


def test_shell_custom_function_arg():
    def f(*args):
        return True

    text = _default_buffer_from_incomplete_run("f ", {"f": f})
    assert text == "f("
    text = _default_buffer_from_incomplete_run("f    ", {"f": f})
    assert text == "f(   "

    def g(par=None):
        return par

    text = _default_buffer_from_incomplete_run("g ", {"g": g})
    assert text == "g("
    text = _default_buffer_from_incomplete_run("g    ", {"g": g})
    assert text == "g(   "


def test_shell_import():
    import bliss

    text = _default_buffer_from_incomplete_run("from bliss.comm ", {"bliss": bliss})
    assert text == "from bliss.comm "
