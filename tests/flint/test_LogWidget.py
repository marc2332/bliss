"""Testing LogWidget."""

import logging
import weakref
from silx.gui.utils.testutils import TestCaseQt
from bliss.flint.widgets.LogWidget import LogWidget

logger = logging.getLogger(__name__)


class TestLogWidget(TestCaseQt):
    def test_logging(self):
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(logger)
        self.assertEqual(widget.logCount(), 0)
        logger.warning("Tout le %s s'eclate", "monde")
        self.qWait()
        logger.error("A la queu%s%s", "leu", "leu")
        self.qWait()
        self.assertEqual(widget.logCount(), 2)
        widget = None

    def test_buggy_logging(self):
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(logger)
        self.assertEqual(widget.logCount(), 0)
        logger.warning("Two fields expected %s %f", "foo")
        logger.warning("Float field expected %f", "foo")
        self.qWait()
        self.assertEqual(widget.logCount(), 2)
        widget = None

    def test_max_logs(self):
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(logger)
        widget.setMaximumLogCount(2)
        self.assertEqual(widget.logCount(), 0)
        logger.warning("A1")
        logger.warning("A1")
        logger.warning("B2")
        logger.warning("B2")
        self.qWait()
        self.assertEqual(widget.logCount(), 2)
        self.assertEqual(widget.toPlainText().count("A1"), 0)
        self.assertEqual(widget.toPlainText().count("B2"), 2)
        widget = None

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
