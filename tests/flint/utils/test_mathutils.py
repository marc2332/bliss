"""Testing mathutils module."""


import numpy
from bliss.flint.utils import mathutils


def test_gaussian_fit():
    xx = numpy.arange(5)
    yy = numpy.array([10, 10, 110, 10, 10])
    r = mathutils.fit_gaussian(xx, yy)

    assert r is not None
    numpy.testing.assert_almost_equal(r.height, 100)
    numpy.testing.assert_almost_equal(r.pos_x, 2)
    numpy.testing.assert_almost_equal(r.background, 10)

    yy2 = r.transform(xx)
    numpy.testing.assert_almost_equal(yy2, yy)
