# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import setup_globals
from bliss.common.standard import wa, wm, sta, stm
from bliss.common.utils import deep_update
import pytest


def test_wa_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    wa()
    captured = capsys.readouterr()
    output = "Current Positions: user\n"
    output += "                   dial\n"
    output += "\n"
    output += "    bad\n"
    output += "-------\n"
    output += "0.00000\n"
    output += "0.00000\n"

    assert captured.out == output


def test_wa_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    wa()
    captured = capsys.readouterr()

    output = "Current Positions: user\n"
    output += "                   dial\n"
    output += "\n"
    output += "bad\n"
    output += "-----\n"
    output += "!ERR\n"
    output += "!ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


@pytest.fixture
def s1hg(default_session):
    s1hg = default_session.config.get("s1hg")
    yield s1hg
    s1hg.__close__()


def test_wa_slits(s1hg, capsys):
    wa()
    captured = capsys.readouterr()

    assert "s1hg" in captured.out
    assert not "s1f" in captured.out
    assert not "s1b" in captured.out


def test_wm_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    wm("bad")
    captured = capsys.readouterr()

    output = "\n"
    output += "              bad\n"
    output += "--------  -------\n"
    output += "User\n"
    output += " High         inf\n"
    output += " Current  0.00000\n"
    output += " Low         -inf\n"
    output += "Offset    0.00000\n"
    output += "\n"
    output += "Dial\n"
    output += " High         inf\n"
    output += " Current  0.00000\n"
    output += " Low         -inf\n"

    assert captured.out == output


def test_wm_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    wm("bad")
    captured = capsys.readouterr()

    output = "\n"
    output += "          bad\n"
    output += "--------  -----\n"
    output += "User\n"
    output += " High     inf\n"
    output += " Current  !ERR\n"
    output += " Low      -inf\n"
    output += "Offset    0\n"
    output += "\n"
    output += "Dial\n"
    output += " High     inf\n"
    output += " Current  !ERR\n"
    output += " Low      -inf\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


def test_sta_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_sta_slits(s1hg, capsys):
    sta()

    captured = capsys.readouterr()

    assert "s1hg" in captured.out
    assert not "s1f" in captured.out
    assert not "s1b" in captured.out


def test_sta_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    sta()
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


def test_stm_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  ---------------------\n"
    output += "bad     READY (Axis is READY)\n"

    assert captured.out == output


def test_stm_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    stm("bad")
    captured = capsys.readouterr()

    output = "Axis    Status\n"
    output += "------  --------\n"
    output += "bad     !ERR\n"

    assert captured.out[: len(output)] == output

    errmsg = "Traceback (most recent call last):\n"
    assert captured.err[: len(errmsg)] == errmsg

    errmsg = "RuntimeError: Error on motor 'bad': BAD POSITION\n"
    assert captured.err[-len(errmsg) :] == errmsg


def test_deep_update():
    source = {"hello1": 1}
    overrides = {"hello2": 2}
    deep_update(source, overrides)
    assert source == {"hello1": 1, "hello2": 2}

    source = {"hello": "to_override"}
    overrides = {"hello": "over"}
    deep_update(source, overrides)
    assert source == {"hello": "over"}

    source = {"hello": {"value": "to_override", "no_change": 1}}
    overrides = {"hello": {"value": "over"}}
    deep_update(source, overrides)
    assert source == {"hello": {"value": "over", "no_change": 1}}

    source = {"hello": {"value": "to_override", "no_change": 1}}
    overrides = {"hello": {"value": {}}}
    deep_update(source, overrides)
    assert source == {"hello": {"value": {}, "no_change": 1}}

    source = {"hello": {"value": {}, "no_change": 1}}
    overrides = {"hello": {"value": 2}}
    deep_update(source, overrides)
    assert source == {"hello": {"value": 2, "no_change": 1}}

    # check for changing types
    source = {"a": 1, "b": 2}
    overrides = {"a": {"value": 2}}
    deep_update(source, overrides)
    assert source == {"a": {"value": 2}, "b": 2}

    # check for correct copying
    subsource = {"hello": {"value": {}, "no_change": 1}}
    source = {"a": 1}
    overrides = {"a": {"value": 2}, "subsource": subsource}
    deep_update(source, overrides)
    assert source == {
        "a": {"value": 2},
        "subsource": {"hello": {"value": {}, "no_change": 1}},
    }
    subsource.pop("hello")
    assert source == {
        "a": {"value": 2},
        "subsource": {"hello": {"value": {}, "no_change": 1}},
    }

    # check references
    class A:
        def __init__(self, arg):
            self.myatt = arg

    a = A("a")
    source = {"a": 1}
    overrides = {"a": a}
    deep_update(source, overrides)
    assert id(a) == id(source["a"])
    overrides = {"a": {"aa": a}}
    deep_update(source, overrides)
    assert id(a) == id(source["a"]["aa"])
