"""Testing LogWidget."""

import logging
import weakref
from silx.gui.utils.testutils import TestCaseQt
from bliss.flint.widgets.LogWidget import LogWidget

logger = logging.getLogger(__name__)


class TestLogWidget(TestCaseQt):

    def test_handler_released_on_destroy(self):
        nb = len(logger.handlers)
        widget = LogWidget()
        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(logger)
        self.assertEqual(len(logger.handlers), nb + 1)

        ref = weakref.ref(widget)
        widget = None
        self.qWaitForDestroy(ref)

        self.assertEqual(len(logger.handlers), nb)
