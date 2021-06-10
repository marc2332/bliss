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


def test_curveplot__bliss_1_8(flint_session):
    """Check custom plot curve API from BLISS <= 1.8"""
    flint = plot.get_flint()
    p = flint.get_plot(plot_class="curve", name="foo-cp")

    data1 = numpy.array([4, 5, 6])
    data2 = numpy.array([2, 5, 2])

    p.add_data({"data1": data1, "data2": data2})
    vrange = p.get_data_range()
    assert vrange == [None, None, None]

    p.select_data("data1", "data2")
    p.select_data("data1", "data2", color="green", symbol="x")
    vrange = p.get_data_range()
    assert vrange == [[4, 6], [2, 5], None]

    p.deselect_data("data1", "data2")
    vrange = p.get_data_range()
    assert vrange == [None, None, None]

    data = p.get_data("data1")
    assert data == pytest.approx(data1)

    p.remove_data("data1")
    data = p.get_data("data1")
    assert data == []


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


def test_plot1d(flint_session):
    f = plot.get_flint()
    p = f.get_plot(plot_class="plot1d", name="plot1d")

    # Check the default data setter
    x = numpy.arange(11) * 2
    y = numpy.arange(11)
    y2 = numpy.arange(11) / 2
    p.add_curve(x=x, y=y, legend="c1", yaxis="left")
    p.add_curve(x=x, y=y2, legend="c2", yaxis="right")
    vrange = p.get_data_range()
    assert vrange == [[0, 20], [0, 10], [0, 5]]

    # Clear the data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange == [None, None, None]

    # Check deprecated API
    x = numpy.arange(11) * 2
    y = numpy.arange(11)
    y2 = numpy.arange(11) / 2
    p.add_data(x, field="x")
    p.add_data(y, field="y")
    p.add_data(y2, field="y2")
    p.select_data("x", "y", yaxis="left")
    p.select_data("x", "y2", yaxis="right")
    vrange = p.get_data_range()
    assert vrange == [[0, 20], [0, 10], [0, 5]]

    # Check the default way to clear data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]


def test_plot2d(flint_session):
    f = plot.get_flint()
    p = f.get_plot(plot_class="plot2d", name="plot2d")

    # Check the default data setter
    image = numpy.arange(10 * 10)
    image.shape = 10, 10
    p.add_image(image)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]

    # FIXME: addImage have to support this API
    # p.set_colormap(lut="viridis", vmin=0, vmax=10)

    # Check the default way to clear data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]

    # Check deprecated API
    image = numpy.arange(9 * 9)
    image.shape = 9, 9
    p.add_data(image, field="image")
    p.select_data("image")
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 9], [0, 9]]

    # Check the default way to clear data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]


def test_scatter_view(flint_session):
    f = plot.get_flint()
    p = f.get_plot(plot_class="scatter", name="scatterview")

    # Check the default data setter
    x = numpy.arange(11)
    y = numpy.arange(11)
    value = numpy.arange(11)
    p.set_data(x=x, y=y, value=value)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]

    # Allow to setup the colormap
    p.set_colormap(lut="viridis", vmin=0, vmax=10)

    # Set none can be use to clear the data
    p.set_data(None, None, None)
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]

    # Check deprecated API
    x = numpy.arange(9)
    y = numpy.arange(9)
    value = numpy.arange(9)
    p.add_data(x, field="x")
    p.add_data(y, field="y")
    p.add_data(value, field="value")
    p.select_data("x", "y", "value")
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 8], [0, 8]]

    # Check the default way to clear data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]


def test_image_view(flint_session):
    f = plot.get_flint()
    p = f.get_plot(plot_class="imageview", name="imageview")

    # Check the default data setter
    image = numpy.arange(10 * 10)
    image.shape = 10, 10
    p.set_data(image)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]

    # Allow to setup the colormap
    p.set_colormap(lut="viridis", vmin=0, vmax=10)

    # Set none can be use to clear the data
    p.set_data(None)
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]

    # Check deprecated API
    image = numpy.arange(9 * 9)
    image.shape = 9, 9
    p.add_data(image, field="image")
    p.select_data("image")
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 9], [0, 9]]

    # Check the default way to clear data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]


def test_image_stack(flint_session):
    f = plot.get_flint()
    p = f.get_plot(plot_class="imagestack", name="imagestack")

    cube = numpy.arange(10 * 10 * 10)
    cube.shape = 10, 10, 10

    # Check the default data setter
    p.set_data(cube)
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]

    # Allow to setup the colormap
    p.set_colormap(lut="viridis", vmin=0, vmax=10)

    # Set none can be use to clear the data
    p.set_data(None)
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]

    # Check deprecated API
    p.add_data(cube, field="cube")
    p.select_data("cube")
    vrange = p.get_data_range()
    assert vrange[0:2] == [[0, 10], [0, 10]]

    # Check the default way to clear data
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange[0:2] == [None, None]


def test_curve_stack(flint_session):
    f = plot.get_flint()
    p = f.get_plot(plot_class="curvestack", name="curve-stack")

    curves = numpy.empty((10, 100))
    for i in range(10):
        curves[i] = numpy.sin(numpy.arange(100) / 30 + i * 6)
    x = numpy.arange(100) * 10

    p.set_data(curves=curves, x=x)
    vrange = p.get_data_range()
    assert vrange[0] == [0, 990]

    p.clear_data()
    vrange = p.get_data_range()
    assert vrange == [None, None]


def test_time_curve_plot(flint_session):
    """Coverage of the main time curve plot API"""
    f = plot.get_flint()

    p = f.get_plot(plot_class="timecurveplot", name="timecurveplot")

    p.select_time_curve("diode1")
    p.select_time_curve("diode2")

    # set_data update the curves
    p.set_data(time=[0, 1, 2], diode1=[0, 1, 1], diode2=[1, 5, 1])
    vrange = p.get_data_range()
    assert vrange[0] == [0, 2]
    assert vrange[1] == [0, 5]

    # append data update the data on the right side
    p.append_data(time=[3], diode1=[2], diode2=[6])
    vrange = p.get_data_range()
    assert vrange[0] == [0, 3]
    assert vrange[1] == [0, 6]

    # when a fixed duration is used, the data disappear on one side
    p.select_x_duration(second=5)
    p.append_data(time=[10], diode1=[2], diode2=[6])
    vrange = p.get_data_range()
    assert vrange[0][0] > 1
    assert vrange[0][1] == 10

    # clean data clean up the plot
    p.clear_data()
    vrange = p.get_data_range()
    assert vrange == [None, None]
