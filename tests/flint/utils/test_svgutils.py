"""Testing LogWidget."""

import pytest
import numpy.testing


from bliss.flint.utils import svgutils


def test_ml_commands():
    expected = numpy.array([[0, 0], [1, 2], [2, 3], [0, 0]])

    path = svgutils.parse_path("M 0,0 L 1,2 L 2,3 z")
    assert len(path) == 1
    assert len(path[0]) == 4
    points = numpy.array(path[0])
    numpy.testing.assert_array_equal(points, expected)

    path = svgutils.parse_path("M 0,0 1,2 2,3 z")
    points = numpy.array(path[0])
    numpy.testing.assert_array_equal(points, expected)

    path = svgutils.parse_path("m 0,0 l 1,2 l 1,1 z")
    points = numpy.array(path[0])
    numpy.testing.assert_array_equal(points, expected)

    path = svgutils.parse_path("m 0,0 1,2 1,1 z")
    points = numpy.array(path[0])
    numpy.testing.assert_array_equal(points, expected)


def test_hv_commands():
    expected = numpy.array([[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]])

    path = svgutils.parse_path("M 0,0 H 2 V 2 h -2 v -2")
    assert len(path) == 1
    assert len(path[0]) == 5
    points = numpy.array(path[0])
    numpy.testing.assert_array_equal(points, expected)


def test_compact_format():
    """No space between command and coords"""
    expected = numpy.array([[1, 2], [1, 2]])

    path = svgutils.parse_path("m1,2 z")
    points = numpy.array(path[0])
    numpy.testing.assert_array_equal(points, expected)


@pytest.mark.parametrize(
    "s",
    [
        "m 0,0 c 10,10",
        "m 0,0 s 10,10",
        "m 0,0 q 10,10",
        "m 0,0 t 10,10",
        "m 0,0 a 10,10",
        "m 0,0 C 10,10",
        "m 0,0 S 10,10",
        "m 0,0 Q 10,10",
        "m 0,0 T 10,10",
        "m 0,0 A 10,10",
    ],
)
def test_unsupported_command(s):
    try:
        svgutils.parse_path(s)
    except ValueError:
        pass
    else:
        assert False
