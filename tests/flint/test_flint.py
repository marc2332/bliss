"""Testing Flint."""

import pytest
from bliss.common import plot


def test_empty_plot(flint):
    p = plot.plot()
    assert 'flint_pid={}'.format(flint) in repr(p)
    assert p.name == 'Plot {}'.format(p._plot_id)

    p = plot.plot(name='Some name')
    assert 'flint_pid={}'.format(flint) in repr(p)
    assert p.name == 'Some name'


def test_simple_plot(flint_session):
    sin = flint_session['sin_data']
    p = plot.plot(sin)
    assert 'CurvePlot' in repr(p)
    data = p.get_data()
    assert data == {
        'default': pytest.approx(sin),
        'x': pytest.approx(range(len(sin)))}


def test_plot_curve_with_x(flint_session):
    sin = flint_session['sin_data']
    cos = flint_session['cos_data']
    p = plot.plot({'sin': sin, 'cos': cos}, x='sin')
    assert 'CurvePlot' in repr(p)
    data = p.get_data()
    assert data == {
        'sin': pytest.approx(sin),
        'cos': pytest.approx(cos)}


def test_image_plot(flint_session):
    grey_image = flint_session['grey_image']
    p = plot.plot(grey_image)
    assert 'ImagePlot' in repr(p)
    data = p.get_data()
    assert data == {
        'default': pytest.approx(grey_image)}
    colored_image = flint_session['colored_image']
    p = plot.plot(colored_image)
    assert 'ImagePlot' in repr(p)
    data = p.get_data()
    assert data == {
        'default': pytest.approx(colored_image)}


def test_curve_plot(flint_session):
    dct = flint_session['sin_cos_dict']
    struct = flint_session['sin_cos_struct']
    scan = flint_session['sin_cos_scan']
    for sin_cos in (dct, struct, scan):
        p = plot.plot(sin_cos)
        assert 'CurvePlot' in repr(p)
        data = p.get_data()
        assert data == {
            'x': pytest.approx(sin_cos['x']),
            'sin': pytest.approx(sin_cos['sin']),
            'cos': pytest.approx(sin_cos['cos'])}
