# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss import setup_globals
from bliss.common.standard import iter_axes_state_all, iter_axes_state
from bliss.common.standard import iter_axes_position_all, iter_axes_position
from bliss.common.standard import info
from bliss.common.utils import deep_update, ErrorWithTraceback
import pytest


def test_wa_normal(default_session):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    assert next(iter_axes_position_all()) == ("bad", None, 0.0, 0.0)


def test_wa_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    out = next(iter_axes_position_all())
    assert out.axis_name == "bad"
    assert isinstance(out.user_position, ErrorWithTraceback)
    assert isinstance(out.dial_position, ErrorWithTraceback)


@pytest.fixture
def s1hg(default_session):
    s1hg = default_session.config.get("s1hg")
    yield s1hg
    s1hg.__close__()


def test_wa_slits(s1hg, capsys):
    out = next(iter_axes_position_all())
    assert out.axis_name == "s1hg"
    assert out.unit is None
    assert out.user_position == 0
    assert out.dial_position == 0


def test_wm_normal(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = False
    out = next(iter_axes_position("bad"))
    inf = float("inf")
    assert out == ("bad", None, 0, inf, -inf, 0, 0, inf, -inf)


def test_wm_exception(default_session, capsys):
    bad = default_session.config.get("bad")
    bad.controller.bad_position = True
    out = next(iter_axes_position("bad"))
    inf = float("inf")
    assert out.axis_name == "bad"
    assert out.unit is None
    assert isinstance(out.user_position, ErrorWithTraceback)
    assert isinstance(out.dial_position, ErrorWithTraceback)
    assert out.user_high_limit == inf == out.dial_high_limit
    assert out.user_low_limit == -inf == out.dial_low_limit
    assert out.offset == 0


def test_info(default_session):
    class TestInfoGood:
        def __info__(self):
            return "good info message"

    class TestInfoBad:
        def __info__(self):
            return 5

    class TestInfoException:
        def __info__(self):
            raise RuntimeError("exception")

    class TestNoInfo:
        pass

    assert info(TestInfoGood()) == "good info message"
    t = TestNoInfo()
    assert info(t) == repr(t)
    with pytest.raises(TypeError):
        info(TestInfoBad())
    with pytest.raises(RuntimeError):
        info(TestInfoException())


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
