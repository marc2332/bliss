# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
from prompt_toolkit.input.defaults import create_pipe_input
from bliss.shell.cli.repl import BlissRepl
import gevent
from bliss.common.utils import autocomplete_property
from types import SimpleNamespace

import pytest
from bliss.shell.cli.repl import _set_pt_event_loop


def _run_incomplete(cmd_input, local_locals):
    _set_pt_event_loop()

    inp = create_pipe_input()

    def mylocals():
        return local_locals

    try:

        br = BlissRepl(
            input=inp, output=None, session="test_session", get_locals=mylocals
        )
        inp.send_text(cmd_input)

        with gevent.Timeout(.5, RuntimeError()):
            br.app.run()
            # this will necessarily result in RuntimeError as the input line is not complete

        assert False  # if we get here the test is pointless
        return None

    except RuntimeError:
        inp.close()
        return br

    inp.close()
    assert False
    return None


def test_shell_signature(clean_gevent, beacon):
    env_dict = dict()
    session = beacon.get("test_session")
    session.setup(env_dict)

    clean_gevent["end-check"] = False

    br = _run_incomplete("ascan(", env_dict)

    sb = [
        n
        for n in br.ptpython_layout.layout.visible_windows
        if "signature_toolbar" in str(n)
    ][0]
    sc = sb.content.text()
    assert ("class:signature-toolbar", "jedi.api.interpreter.ascan") not in sc
    assert ("class:signature-toolbar", "ascan") in sc

    session.close()


def test_shell_kwarg_signature(clean_gevent):

    env_dict = dict()

    clean_gevent["end-check"] = False

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

    br = _run_incomplete("b.f(", {"b": loc["b"]})

    sb = [
        n
        for n in br.ptpython_layout.layout.visible_windows
        if "signature_toolbar" in str(n)
    ][0]
    sc = sb.content.text()

    assert ("class:signature-toolbar", "param mykw=12") in sc


def _get_completion(br):
    cl = [
        n
        for n in br.ptpython_layout.layout.visible_windows
        if "MultiColumnCompletionMenuControl" in str(n)
    ]
    if cl == []:
        return {}
    else:
        return {cc.text for cc in cl[0].content._render_pos_to_completion.values()}


def test_shell_autocomplete_property(clean_gevent):
    clean_gevent["end-check"] = False

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

    br = _run_incomplete("tpc.", {"tpc": tpc})
    completions = _get_completion(br)
    assert "x" in completions
    assert "y" in completions
    assert "z" in completions
    del (br)

    br = _run_incomplete("tpc.x.", {"tpc": tpc})
    completions = _get_completion(br)
    assert "b" in completions

    br = _run_incomplete("tpc.y.", {"tpc": tpc})
    completions = _get_completion(br)
    assert completions == {}

    br = _run_incomplete("tpc.z.", {"tpc": tpc})
    completions = _get_completion(br)
    assert "b" in completions


def test_shell_comma_object(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print self \r", {})
    assert br.default_buffer.text == "print(self,\n"


def test_shell_comma_after_comma_inside_callable(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print(1, ", {})
    assert br.default_buffer.text == "print(1, "


def test_shell_comma_int(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print 1 ", {})
    assert br.default_buffer.text == "print(1,"


def test_shell_comma_float(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print 1.1 ", {})
    assert br.default_buffer.text == "print(1.1,"


def test_shell_comma_bool(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print False ", {})
    assert br.default_buffer.text == "print(False,"


def test_shell_comma_string(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print 'bla' ", {})
    assert br.default_buffer.text == "print('bla',"


def test_shell_comma_kwarg(clean_gevent):
    clean_gevent["end-check"] = False
    br = _run_incomplete("print run=True ", {})
    assert br.default_buffer.text == "print(run=True,"


def test_shell_custom_function_kwarg(clean_gevent):
    clean_gevent["end-check"] = False

    def f(**kwargs):
        return True

    br = _run_incomplete("f ", {"f": f})
    assert br.default_buffer.text == "f("


def test_shell_custom_function_arg(clean_gevent):
    clean_gevent["end-check"] = False

    def f(*args):
        return True

    br = _run_incomplete("f ", {"f": f})
    assert br.default_buffer.text == "f("
    br = _run_incomplete("f    ", {"f": f})
    assert br.default_buffer.text == "f(   "

    def g(par=None):
        return par

    br = _run_incomplete("g ", {"g": g})
    assert br.default_buffer.text == "g("
    br = _run_incomplete("g    ", {"g": g})
    assert br.default_buffer.text == "g(   "


def test_shell_import(clean_gevent):
    clean_gevent["end-check"] = False
    import bliss

    br = _run_incomplete("from bliss.comm ", {"bliss": bliss})
    assert br.default_buffer.text == "from bliss.comm "
