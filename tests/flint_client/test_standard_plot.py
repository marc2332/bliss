"""Testing the common plot API provided by BLISS."""

import numpy
from bliss.common import plot


def test_plot_list(flint_session):
    data = [0, 1, 2, 0, 1, 2]
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 5], [0, 2]]


def test_scatter_plot(flint_session):
    x = numpy.array([0, 1, 2, 0, 1, 2, 0, 1, 2])
    y = numpy.array([0, 0, 0, 1, 1, 1, 2, 2, 2])
    value = numpy.array([0, 1, 0, 1, 2, 1, 0, 1, 0])
    p = plot.plot_scatter(x, y, value)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 2], [0, 2]]


def test_plot_numpy_1d(flint_session):
    data = numpy.array([0, 1, 2, 0, 1, 2])
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 5], [0, 2]]


def test_plot_structured_numpy_1d(flint_session):
    dtype = [("x", float), ("v1", float), ("v2", float)]
    data = numpy.array([(0, 5, 6), (1, 6, 5), (2, 5, 6), (3, 6, 5)], dtype=dtype)
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 3], [5, 6]]


def test_plot_dict(flint_session):
    x = numpy.array([0, 1, 2, 3, 4, 5])
    y = numpy.array([5, 6, 5, 6, 5, 6])
    data = {"x": x, "y": y}
    p = plot.plot(data)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 5], [5, 6]]


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
