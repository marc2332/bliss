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
