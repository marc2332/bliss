"""Testing custom plots provided by Flint."""

from bliss.common import plot


def test_select_points(flint_session):
    flint = plot.get_flint()
    p = plot.plot()

    # 'select' lock reentrant calls, execusion have to be planed before
    # This requests to click later, good luck
    flint.click_on_plot(p.plot_id, relative_to_center=True, delay=4000)
    result = p.select_points(1)
    assert len(result) == 1
    assert len(result[0]) == 2


def test_select_shape(flint_session):
    flint = plot.get_flint()
    p = plot.plot()

    # 'select' lock reentrant calls, execusion have to be planed before
    # This requests to click later, good luck
    flint.click_on_plot(p.plot_id, relative_to_center=True, delay=4000)
    flint.click_on_plot(p.plot_id, relative_to_center=True, delta=[5, 5], delay=5000)
    result = p.select_shape(shape="line")
    assert len(result) == 2
    assert len(result[0]) == 2
    assert len(result[1]) == 2
