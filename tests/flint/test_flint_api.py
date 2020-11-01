"""Testing LogWidget."""

import logging
import pytest
import numpy
import pickle

from silx.gui import qt  # noqa: F401
from silx.gui.utils.testutils import TestCaseQt
from bliss.common import plot
from bliss.flint.client import plots
from bliss.controllers.lima import roi as lima_roi

logger = logging.getLogger(__name__)


@pytest.mark.skip(reason="This test often segfault the bcu-ci")
@pytest.mark.usefixtures("flint_norpc")
class TestFlint(TestCaseQt):
    def test_empty_plot(self):
        p = plot.plot()
        pid = plot.get_flint()._pid
        assert "flint_pid={}".format(pid) in repr(p)
        assert p.name == "Plot {}".format(p._plot_id)

        p = plot.plot(name="Some name")
        assert "flint_pid={}".format(pid) in repr(p)
        assert p.name == "Some name"

    def test_remove_custom_plot(self):
        flint = plot.get_flint()
        p = flint.get_plot(plot_class="curve", name="foo-rm")
        flint.remove_plot(p.plot_id)
        assert flint.is_plot_exists("foo-rm") is False

    def test_custom_plot_curveplot(self):
        widget = plots.CurvePlot(name="foo")

        cos_data = numpy.cos(numpy.linspace(0, 2 * numpy.pi, 10))
        sin_data = numpy.sin(numpy.linspace(0, 2 * numpy.pi, 10))

        widget.add_data({"cos": cos_data, "sin": sin_data})
        widget.select_data("sin", "cos")
        widget.select_data("sin", "cos", color="green", symbol="x")
        widget.deselect_data("sin", "cos")
        widget.clear_data()


def test_used_object():
    """Make sure object shared in the RPC are still picklable"""
    roi = lima_roi.ArcRoi(0, 1, 2, 3, 4, 5, 6)
    pickle.loads(pickle.dumps(roi))
    roi = lima_roi.Roi(0, 1, 2, 3)
    pickle.loads(pickle.dumps(roi))
    roi = lima_roi.RoiProfile(0, 1, 2, 3, mode="vertical")
    pickle.loads(pickle.dumps(roi))
