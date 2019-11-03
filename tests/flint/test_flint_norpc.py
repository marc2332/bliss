"""Testing LogWidget."""

import logging
import pytest
import numpy

from silx.gui import qt
from silx.gui.utils.testutils import TestCaseQt
from bliss.flint import flint
from bliss.common import plot

logger = logging.getLogger(__name__)


def get_real_flint(*args, **kwargs):
    settings = qt.QSettings()
    flint_model = flint.create_flint_model(settings)
    interface = flint_model.flintApi()
    interface._pid = -666
    return interface


@pytest.mark.usefixtures("xvfb", "beacon")
class TestFlint(TestCaseQt):
    def setUp(self):
        flint.initApplication([])
        self.old_get_flint = plot.get_flint
        plot.get_flint = get_real_flint
        TestCaseQt.setUp(self)

    def tearDown(self):
        plot.get_flint = self.old_get_flint
        self.old_get_flint = None
        TestCaseQt.tearDown(self)

    def test_empty_plot(self):
        p = plot.plot()
        pid = plot.get_flint()._pid
        assert "flint_pid={}".format(pid) in repr(p)
        assert p.name == "Plot {}".format(p._plot_id)

        p = plot.plot(name="Some name")
        assert "flint_pid={}".format(pid) in repr(p)
        assert p.name == "Some name"

    def test_remove_custom_plot(self):
        widget = plot.CurvePlot(name="foo-rm")
        plot_id = widget.plot_id
        flint_api = widget._flint
        flint_api.remove_plot(plot_id)

    def test_custom_plot_curveplot(self):
        widget = plot.CurvePlot(name="foo")

        cos_data = numpy.cos(numpy.linspace(0, 2*numpy.pi, 10))
        sin_data = numpy.sin(numpy.linspace(0, 2*numpy.pi, 10))

        widget.add_data({'cos': cos_data, 'sin': sin_data})
        widget.select_data('sin', 'cos')
        widget.select_data('sin', 'cos', color='green', symbol='x')
        widget.deselect_data('sin', 'cos')
        widget.clear_data()
