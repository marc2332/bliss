"""Testing custom plots provided by Flint."""

import gevent
from bliss.common import plot


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


def test_select_shapes(flint_session):
    flint = plot.get_flint()
    p = plot.plot()
    context = []

    def active_gui():
        result = p.select_shapes()
        context.append(result)

    def do_actions():
        gevent.sleep(1)
        flint.test_active(p.plot_id, qaction="roi-select-rectangle")
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
