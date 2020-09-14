# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import gevent
import os
import contextlib
import greenlet

from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.eventloop import get_event_loop
from types import SimpleNamespace

from bliss.shell.cli.repl import BlissRepl
from bliss.common.utils import autocomplete_property


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
    inp = create_pipe_input()

    def mylocals():
        return local_locals

    br = BlissRepl(input=inp, output=None, session="test_session", get_locals=mylocals)
    inp.send_text(cmd_input)

    class RunAborted(BaseException):
        pass

    data = {}
    data["greenlet"] = greenlet.getcurrent()

    def abort_app():
        """Abort the app.run call"""
        current = data["greenlet"]
        current.throw(RunAborted)

    if stop_condition is None:
        # There is no end condition cause no result is expected
        # So reduce the timeout, cause we could wait forever
        timeout = 3
    else:
        timeout = 10

    @contextlib.contextmanager
    def hooked_render():
        """Context manager to add a hook in the prompt_toolkit renderer.

        The hook test a condition to allow to abort the application execution.
        """
        from prompt_toolkit.renderer import Renderer

        old_function = Renderer.render

        def new_function(self, *args, **kwargs):
            old_function(self, *args, **kwargs)
            if stop_condition is not None and stop_condition(br):
                data["abort"] = gevent.spawn(abort_app)

        Renderer.render = new_function
        try:
            yield
        finally:
            Renderer.render = old_function

    try:
        # Make sure the run have a termination
        with gevent.Timeout(timeout):
            with hooked_render():
                # Blocking call
                br.app.run(set_exception_handler=False)
            # Unreachable code
            raise RuntimeError("Unreachable code hit: fix the test")
    except gevent.Timeout:
        # Ultimate check
        if stop_condition is None or stop_condition(br):
            pass
        else:
            raise RuntimeError("Unterminated app run")
    except RunAborted:
        pass
    finally:
        if "abort" in data:
            data["abort"].kill()
        data = None
        inp.close()
        get_event_loop().close()
    return br


def _signature_toolbar_from_incomplete_run(command, env_dict):
    def is_completed(br):
        sb = [
            n
            for n in br.ptpython_layout.layout.visible_windows
            if "signature_toolbar" in str(n)
        ]
        return len(sb) >= 1

    br = _run_incomplete(command, env_dict, stop_condition=is_completed)
    sb = [
        n
        for n in br.ptpython_layout.layout.visible_windows
        if "signature_toolbar" in str(n)
    ][0]
    return sb


def _completion_from_incomplete_run(command, env_dict, no_condition=False):
    def is_completed(br):
        cl = [
            n
            for n in br.ptpython_layout.layout.visible_windows
            if "MultiColumnCompletionMenuControl" in str(n)
        ]
        return len(cl) >= 1

    if no_condition:
        is_completed = None

    br = _run_incomplete(command, env_dict, stop_condition=is_completed)
    cl = [
        n
        for n in br.ptpython_layout.layout.visible_windows
        if "MultiColumnCompletionMenuControl" in str(n)
    ]
    if len(cl) == 0:
        return {}
    return {cc.text for cc in cl[0].content._render_pos_to_completion.values()}


def _default_buffer_from_incomplete_run(command, env_dict):
    data = {}
    data["input"] = 0

    def on_second_render(br):
        if data["input"] >= 1:
            return True
        data["input"] = data["input"] + 1
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


def test_shell_signature(beacon):
    with session_env_dict(beacon, "test_session") as env_dict:
        sb = _signature_toolbar_from_incomplete_run("ascan(", env_dict)
        sc = sb.content.text()
        assert ("class:signature-toolbar", "jedi.api.interpreter.ascan") not in sc
        assert ("class:signature-toolbar", "ascan") in sc


def test_shell_completion(clean_gevent, beacon):
    with session_env_dict(beacon, "test_session5") as env_dict:
        c = _completion_from_incomplete_run("m", env_dict)
        assert "m2" in c


def test_shell_hide_private_completion(clean_gevent, beacon):
    with session_env_dict(beacon, "test_session5") as env_dict:
        c = _completion_from_incomplete_run("test_session5.", env_dict)
        assert "_load_config" not in c
        c = _completion_from_incomplete_run("test_session5._", env_dict)
        assert "_load_config" in c


def test_shell_load_script(clean_gevent, beacon):
    with session_env_dict(beacon, "test_session5") as env_dict:
        c = _completion_from_incomplete_run("tes", env_dict)
        assert "test1" in c


def test_shell_load_script_signature(clean_gevent, beacon):
    with session_env_dict(beacon, "test_session5") as env_dict:
        env_dict["user_script_homedir"](str(os.path.dirname(__file__)))
        env_dict["user_script_load"]("script", export_global="x")

        x = env_dict["x"]

        assert "MyClass" in dir(x)
        assert "myfunc" in dir(x)

        mc = x.MyClass()

        sb = _signature_toolbar_from_incomplete_run("mc.myfunc(", {"x": x, "mc": mc})
        sc = sb.content.text()
        assert ("class:signature-toolbar", "kwarg=14") in sc

        sb = _signature_toolbar_from_incomplete_run("x.myfunc(", {"x": x, "mc": mc})
        sc = sb.content.text()
        assert ("class:signature-toolbar", "kwarg=13") in sc


def test_shell_load_script2(clean_gevent, beacon):
    with session_env_dict(beacon, "test_session") as env_dict:
        c = _completion_from_incomplete_run("vis", env_dict)
        assert "visible_func" in c


def _test_shell_load_script_error(clean_gevent, beacon, capsys):
    with session_env_dict(beacon, "test_session5") as env_dict:
        _br = _run_incomplete("test1 ", env_dict)
        out, _err = capsys.readouterr()

        assert "Unhandled exception in event loop" not in out


def test_shell_kwarg_signature(clean_gevent):
    loc = dict()
    exec(
        """
class B():
    def f(self,arg,mykw=12):
        pass
b=B()
    """,
        None,
        loc,
    )

    sb = _signature_toolbar_from_incomplete_run("b.f(", {"b": loc["b"]})
    sc = sb.content.text()
    assert ("class:signature-toolbar", "mykw=12") in sc


def test_shell_autocomplete_property():
    class Test_property_class:
        def __init__(self):
            self.x = SimpleNamespace(**{"b": 1})

        @property
        def y(self):
            return self.x

        @autocomplete_property
        def z(self):
            return self.x

    tpc = Test_property_class()

    c = _completion_from_incomplete_run("tpc.", {"tpc": tpc})
    assert "x" in c
    assert "y" in c
    assert "z" in c

    c = _completion_from_incomplete_run("tpc.x.", {"tpc": tpc})
    assert "b" in c

    c = _completion_from_incomplete_run("tpc.y.", {"tpc": tpc}, no_condition=True)
    assert c == {}

    c = _completion_from_incomplete_run("tpc.z.", {"tpc": tpc})
    assert "b" in c


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


def test_short_signature():

    loc = dict()
    exec(
        """
class Test:
    from bliss.common.utils import shorten_signature
    import typeguard
    from typing import Optional

    @shorten_signature(annotations={"b": "True|False"}, hidden_kwargs=["d"])
    @typeguard.typechecked
    def func(
        self,
        a: int,
        b: Optional[str] = None,
        c: Optional[str] = None,
        d: Optional[str] = None,
    ):
        pass

t = Test()
    """,
        None,
        loc,
    )

    sb = _signature_toolbar_from_incomplete_run("t.func(", {"t": loc["t"]})
    _sc = sb.content.text()
    display_sig = "".join([x[1] for x in sb.content.text()])
    assert display_sig == " func(a, b: 'True|False'=None, c=None) "
