from bliss.common.utils import flatten, merge
import numpy


def test_flatten():
    assert flatten([1, 2, [3, 4, 5]]) == [1, 2, 3, 4, 5]
    assert flatten([1, 2, [3, 4, numpy.array((4, 5, 6))]]) == [1, 2, 3, 4, 4, 5, 6]
    assert flatten([1]) == [1]
    assert flatten([1, 3, 6]) == [1, 3, 6]


def test_merge():
    assert merge([[1, 2], [3]]) == [1, 2, 3]
    assert merge([[1, 2], [[3, 4]], [5]]) == [1, 2, [3, 4], 5]
