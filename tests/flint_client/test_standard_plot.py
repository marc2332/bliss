"""Testing the common plot API provided by BLISS."""

import numpy
from bliss.common import plot


def test_plot_list(flint_session):
    data = [0, 1, 2, 0, 1, 2]
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 5], [0, 2]]


def test_plot_numpy_1d(flint_session):
    data = numpy.array([0, 1, 2, 0, 1, 2])
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 5], [0, 2]]


def test_plot_numpy_2d(flint_session):
    data = numpy.arange(10 * 10)
    data.shape = 10, 10
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]


def test_plot_numpy_3d(flint_session):
    data = numpy.arange(10 * 10 * 10)
    data.shape = 10, 10, 10
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]
