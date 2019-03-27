# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import sys

from prompt_toolkit.input.defaults import create_pipe_input
from bliss.shell.cli.repl import BlissRepl
from prompt_toolkit.output import DummyOutput
import gevent


def test_shell_signature(clean_gevent, beacon):
    env_dict = dict()
    session = beacon.get("test_session")
    session.setup(env_dict)

    clean_gevent["end-check"] = False

    inp = create_pipe_input()

    def mylocals():
        return env_dict

    try:
        br = BlissRepl(
            input=inp, output=DummyOutput(), session="test_session", get_locals=mylocals
        )
        inp.send_text("ascan(")

        with gevent.Timeout(.1, RuntimeError()):
            br.app.run()
            # this will necessarily result in RuntimeError as the input line is not complete

        assert False  # if we get here the test is pointless

    except RuntimeError:
        sb = [
            n
            for n in br.ptpython_layout.layout.visible_windows
            if "signature_toolbar" in str(n)
        ][0]
        sc = sb.content.text()
        assert ("class:signature-toolbar", "jedi.api.interpreter.ascan") not in sc
        assert ("class:signature-toolbar", "ascan") in sc

    finally:
        inp.close()
    session.close()
