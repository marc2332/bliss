"""Testing live window."""

import pytest
import contextlib

from silx.gui.utils.testutils import TestCaseQt
from silx.gui import qt

from bliss.flint.widgets.live_window import LiveWindow
from bliss.flint.model import flint_model


@pytest.mark.usefixtures("local_flint")
class TestLiveWindow(TestCaseQt):
    def create_flint_model(self):
        flint = flint_model.FlintState()
        workspace = flint_model.Workspace(flint)
        flint.setWorkspace(workspace)
        return flint

    @contextlib.contextmanager
    def use_widget(self):
        flint = self.create_flint_model()
        widget = LiveWindow()
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        widget.setFlintModel(flint)
        yield widget
        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.close()
        widget.deleteLater()
        widget = None
        self.qWait(10)

    def test_display_nothing(self):
        # Construct the widget
        with self.use_widget():
            pass

    def test_feed_default_layout(self):
        # Construct the widget
        with self.use_widget() as widget:
            flintModel = widget.flintModel()
            workspace = flintModel.workspace()
            widget.feedDefaultWorkspace(flintModel, workspace)

    def test_window_actions(self):
        # Test all the actions
        self.allowedLeakingWidgets = 30
        with self.use_widget() as widget:
            menu = qt.QMenu()
            widget.createWindowActions(menu)
            for action in menu.actions():
                if action.isCheckable():
                    action.trigger()
                    self.qWait(200)
                    action.trigger()
                    self.qWait(200)
                else:
                    action.trigger()
                    self.qWait(200)

    def test_layout_actions(self):
        # Test all the actions
        self.allowedLeakingWidgets = 30
        with self.use_widget() as widget:
            actions = widget.createLayoutActions(widget)
            for action in actions:
                if action.isCheckable():
                    action.trigger()
                    self.qWait(200)
                    action.trigger()
                    self.qWait(200)
                else:
                    action.trigger()
                    self.qWait(200)
