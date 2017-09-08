"""Test module for XIA INI file parsing."""

from collections import OrderedDict

import pytest

from bliss.controllers.mca.handel.parser import parse_xia_ini_file as parse


def test_simple():
    content = """\
[s1]

START #0
a = 1
b = 2
END #0

START #1
c = 3
d = 4
END #1

[s2]

START #0
e = 5
f = 6
END #0

START #1
g = 7
h = 8
END #1
"""
    conf = parse(content)
    expected = OrderedDict(
        [
            (
                "s1",
                [
                    OrderedDict([("a", "1"), ("b", "2")]),
                    OrderedDict([("c", "3"), ("d", "4")]),
                ],
            ),
            (
                "s2",
                [
                    OrderedDict([("e", "5"), ("f", "6")]),
                    OrderedDict([("g", "7"), ("h", "8")]),
                ],
            ),
        ]
    )
    assert conf == expected


def test_invalid_line():
    content = "hello!"
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "Line not recognized: 'hello!'" in str(ctx.value)


def test_item_outside_of_section():
    content = """\
START #0
a = 1
END #0"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "Item 0 outside of section" in str(ctx.value)


def test_end_markup_outside_of_item():
    content = """\
END #0"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "End markup outside of item" in str(ctx.value)


def test_corrupted_start():
    content = """\
[s1]
START #1
a = 1
END #1"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "Corrupted start (section s1, 1 should be 0)" in str(ctx.value)


def test_corrupted_end():
    content = """\
[s1]
START #0
a = 1
END #1"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "Corrupted end (section s1, 1 should be 0)" in str(ctx.value)


def test_new_section_in_item():
    content = """\
[s1]
START #0
a = 1
[s2]
END #0"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "New section within section s1 item 0" in str(ctx.value)


def test_new_item_in_item():
    content = """\
[s1]
START #0
a = 1

START #1
b = 2
END #1

END #0"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "New item within section s1 item 0" in str(ctx.value)


def test_pair_outside_of_item():
    content = """\
[s1]
a = 1
"""
    with pytest.raises(ValueError) as ctx:
        parse(content)
    assert "Key/value pair ('a', '1') outside of item" in str(ctx.value)
