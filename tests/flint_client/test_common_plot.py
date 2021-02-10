"""Testing the BLISS bliss.common.plot API."""

import pytest
import numpy
from bliss.common import plot


def test_empty_plot(flint_session):
    p = plot.plot(name="Foo")
    pid = plot.get_flint()._pid
    assert "flint_pid={}".format(pid) in repr(p)
    assert p.name == "Foo"

    p = plot.plot(name="Some name")
    assert "flint_pid={}".format(pid) in repr(p)
    assert p.name == "Some name"


def test_reuse_custom_plot__api_1_0(flint_session):
    """Test reuse of custom plot from an ID"""
    widget = plot.plot_curve(name="foo")
    cos_data = numpy.cos(numpy.linspace(0, 2 * numpy.pi, 10))
    widget.add_data({"cos": cos_data, "foo": cos_data})
    widget2 = plot.plot_curve(name="foo", existing_id=widget.plot_id)
    cos = widget2.get_data()["cos"]
    numpy.testing.assert_allclose(cos, cos_data)


def test_reuse_custom_plot__api_1_6(flint_session):
    """Test reuse of custom plot from a name"""
    widget = plot.plot_curve(name="foo", existing_id="myplot")
    cos_data = numpy.cos(numpy.linspace(0, 2 * numpy.pi, 10))
    widget.add_data({"cos": cos_data, "foo": cos_data})
    widget2 = plot.plot_curve(name="foo", existing_id="myplot")
    cos = widget2.get_data()["cos"]
    numpy.testing.assert_allclose(cos, cos_data)


def test_simple_plot(flint_session):
    sin = flint_session.env_dict["sin_data"]
    p = plot.plot(sin)
    assert "Plot1D" in repr(p)
    data = p.get_data()
    assert data == {
        "default": pytest.approx(sin),
        "x": pytest.approx(list(range(len(sin)))),
    }


def test_plot_curve_with_x(flint_session):
    sin = flint_session.env_dict["sin_data"]
    cos = flint_session.env_dict["cos_data"]
    p = plot.plot({"sin": sin, "cos": cos}, x="sin")
    assert "Plot1D" in repr(p)
    data = p.get_data()
    assert data == {"sin": pytest.approx(sin), "cos": pytest.approx(cos)}


def test_image_plot(flint_session):
    grey_image = flint_session.env_dict["grey_image"]
    p = plot.plot(grey_image)
    assert "Plot2D" in repr(p)
    data = p.get_data()
    assert data == {"default": pytest.approx(grey_image)}
    colored_image = flint_session.env_dict["colored_image"]
    p = plot.plot(colored_image)
    assert "Plot2D" in repr(p)
    data = p.get_data()
    assert data == {"default": pytest.approx(colored_image)}


def test_curve_plot(flint_session):
    dct = flint_session.env_dict["sin_cos_dict"]
    struct = flint_session.env_dict["sin_cos_struct"]
    scan = flint_session.env_dict["sin_cos_scan"]
    for sin_cos in (dct, struct, scan):
        p = plot.plot(sin_cos)
        assert "Plot1D" in repr(p)
        data = p.get_data()
        assert data == {
            "x": pytest.approx(sin_cos["x"]),
            "sin": pytest.approx(sin_cos["sin"]),
            "cos": pytest.approx(sin_cos["cos"]),
        }
