"""Testing LogWidget."""

import logging
import pytest
from silx.gui import qt
from silx.gui.utils.testutils import TestCaseQt
from bliss.flint import flint
from bliss.common import plot

logger = logging.getLogger(__name__)


def get_real_flint(*args, **kwargs):
    settings = qt.QSettings()
    interface = flint.create_flint(settings)
    interface._pid = -666
    return interface


@pytest.mark.usefixtures("xvfb")
class TestFlint(TestCaseQt):
    def setUp(self):

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
        print(repr(p))
        assert "flint_pid={}".format(pid) in repr(p)
        assert p.name == "Plot {}".format(p._plot_id)

        p = plot.plot(name="Some name")
        assert "flint_pid={}".format(pid) in repr(p)
        assert p.name == "Some name"
