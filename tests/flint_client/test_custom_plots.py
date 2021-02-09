"""Testing custom plots provided by Flint."""

import pytest
import gevent
import numpy
from bliss.common import plot
from bliss.controllers.lima import roi as lima_roi


def test_empty_plot(flint_session):
    flint = plot.get_flint()
    p = flint.get_plot(plot_class="curve", name="foo-empty")
    assert flint.is_plot_exists("foo-empty") is False
    assert p is not None


def test_remove_custom_plot(flint_session):
    flint = plot.get_flint()
    p = flint.get_plot(plot_class="curve", name="foo-rm")
    flint.remove_plot(p.plot_id)
    assert flint.is_plot_exists("foo-rm") is False


def test_custom_plot_curveplot(flint_session):
    flint = plot.get_flint()
    p = flint.get_plot(plot_class="curve", name="foo-cp")

    cos_data = numpy.cos(numpy.linspace(0, 2 * numpy.pi, 10))
    sin_data = numpy.sin(numpy.linspace(0, 2 * numpy.pi, 10))

    p.add_data({"cos": cos_data, "sin": sin_data})
    p.select_data("sin", "cos")
    p.select_data("sin", "cos", color="green", symbol="x")
    p.deselect_data("sin", "cos")
    p.remove_data("sin")

    data = p.get_data("cos")
    assert data == pytest.approx(cos_data)

    p.clear_data()


def test_reuse_custom_plot(flint_session):
    flint = plot.get_flint()
    p = flint.get_plot(plot_class="curve", unique_name="foo-reuse")
    cos_data = numpy.cos(numpy.linspace(0, 2 * numpy.pi, 10))
    p.add_data({"cos": cos_data})
    p2 = flint.get_plot(plot_class="curve", unique_name="foo-reuse")
    data = p2.get_data("cos")
    assert data == pytest.approx(cos_data)


def test_select_points(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []

    def active_gui():
        result = p.select_points(1)
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_mouse(
            p.plot_id, mode="click", position=(0, 0), relative_to_center=True
        )

    gevent.joinall([gevent.spawn(f) for f in [active_gui, do_actions]])
    assert len(context) == 1

    result = context[0]
    assert len(result) == 1
    assert len(result[0]) == 2


def test_select_shape(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []

    def active_gui():
        result = p.select_shape(shape="line")
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_mouse(
            p.plot_id, mode="click", position=(0, 0), relative_to_center=True
        )
        flint.test_mouse(
            p.plot_id, mode="click", position=(5, 5), relative_to_center=True
        )

    gevent.joinall([gevent.spawn(f) for f in [active_gui, do_actions]])
    assert len(context) == 1

    result = context[0]
    assert len(result) == 2
    assert len(result[0]) == 2
    assert len(result[1]) == 2


def test_select_shapes__rect(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []

    def active_gui():
        result = p.select_shapes()
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_mouse(
            p.plot_id, mode="press", position=(-5, -5), relative_to_center=True
        )
        flint.test_mouse(
            p.plot_id, mode="release", position=(5, 5), relative_to_center=True
        )
        flint.test_active(p.plot_id, qaction="roi-apply-selection")

    gevent.joinall([gevent.spawn(f) for f in [active_gui, do_actions]])
    assert len(context) == 1

    result = context[0]
    assert len(result) == 1
    roi = result[0]
    assert isinstance(roi, dict)
    expected_keys = set(["origin", "size", "label", "kind"])
    assert len(expected_keys - roi.keys()) == 0
    assert roi["kind"] == "Rectangle"


def test_select_shapes__arc(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []

    def active_gui():
        result = p.select_shapes(kinds=["lima-arc"])
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_mouse(
            p.plot_id, mode="press", position=(-5, -5), relative_to_center=True
        )
        flint.test_mouse(
            p.plot_id, mode="release", position=(5, 5), relative_to_center=True
        )
        flint.test_active(p.plot_id, qaction="roi-apply-selection")

    gevent.joinall([gevent.spawn(f) for f in [active_gui, do_actions]])
    assert len(context) == 1

    result = context[0]
    assert len(result) == 1
    roi = result[0]
    assert isinstance(roi, lima_roi.ArcRoi)


def test_select_shapes__rect_profile(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []

    def active_gui():
        result = p.select_shapes(kinds=["lima-vertical-profile"])
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_mouse(
            p.plot_id, mode="press", position=(-5, -5), relative_to_center=True
        )
        flint.test_mouse(
            p.plot_id, mode="release", position=(5, 5), relative_to_center=True
        )
        flint.test_active(p.plot_id, qaction="roi-apply-selection")

    gevent.joinall([gevent.spawn(f) for f in [active_gui, do_actions]])
    assert len(context) == 1

    result = context[0]
    assert len(result) == 1
    roi = result[0]
    assert isinstance(roi, lima_roi.RoiProfile)
    assert roi.mode == "vertical"


def test_select_shapes__initial_selection(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []
    roi_dict = dict(origin=(1, 2), size=(3, 4), kind="Rectangle", label="roi_dict")
    roi_rect = lima_roi.Roi(0, 1, 2, 3, name="roi_rect")
    roi_arc = lima_roi.ArcRoi(0, 1, 2, 3, 4, 5, name="roi_arc")
    roi_profile = lima_roi.RoiProfile(0, 1, 2, 3, mode="vertical", name="roi_profile")

    def active_gui():
        result = p.select_shapes(
            initial_selection=[roi_dict, roi_rect, roi_arc, roi_profile]
        )
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_active(p.plot_id, qaction="roi-apply-selection")

    gevent.joinall([gevent.spawn(f) for f in [active_gui, do_actions]])
    assert len(context) == 1

    rois = context[0]
    assert len(rois) == 4
    assert rois[0]["label"] == roi_dict["label"]
    assert rois[1].name == roi_rect.name
    assert rois[2].name == roi_arc.name
    assert rois[3].name == roi_profile.name
