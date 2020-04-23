import numpy
from bliss.common.utils import flatten, merge, ShellStr, prudent_update


def test_flatten():
    assert flatten([1, 2, [3, 4, 5]]) == [1, 2, 3, 4, 5]
    assert flatten([1, 2, [3, 4, numpy.array((4, 5, 6))]]) == [1, 2, 3, 4, 4, 5, 6]
    assert flatten([1]) == [1]
    assert flatten([1, 3, 6]) == [1, 3, 6]


def test_merge():
    assert merge([[1, 2], [3]]) == [1, 2, 3]
    assert merge([[1, 2], [[3, 4]], [5]]) == [1, 2, [3, 4], 5]


def test_shell_str():
    raw_s = "<hi>"
    s = ShellStr(raw_s)
    assert s.__info__() == raw_s


def test_prudent_update_raw_0():
    d = {"a": {"b": [1, 2, 3]}}
    e = {"a": {"b": [2, 2, 3, 4]}}
    d = prudent_update(d, e)
    assert len(d["a"]["b"]) == 4
    assert d["a"]["b"][0] == 2
    assert d["a"]["b"][3] == 4


def test_prudent_update_raw_1():
    d = {"a": {"b": [1, 5, 3]}}
    e = {"a": {"b": [4, 5]}}
    d = prudent_update(e, d)
    assert d["a"]["b"] == [1, 5, 3]
