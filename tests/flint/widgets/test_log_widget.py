"""Testing LogWidget."""

import logging
import weakref
import pytest
from silx.gui.utils.testutils import TestCaseQt
from bliss.flint.widgets.log_widget import LogWidget

logger = logging.getLogger(__name__)


@pytest.mark.usefixtures("xvfb")
class TestLogWidget(TestCaseQt):
    def plain_text(self, widget):
        model = widget.model()
        text = ""
        for i in range(model.rowCount()):
            index = model.index(i, widget.MessageColumn)
            item = model.itemFromIndex(index)
            if text != "":
                text += "\n"
            text += item.text()
        return text

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

        plainText = self.plain_text(widget)
        self.assertEqual(plainText.count("A1"), 0)
        self.assertEqual(plainText.count("B2"), 2)
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

    def test_causes(self):
        """Coverage with exception containing causes"""
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(logger)

        try:
            try:
                try:
                    raise IndexError("AAA")
                except Exception as e:
                    raise RuntimeError("BBB") from e
            except Exception as e:
                raise RuntimeError("CCC") from e
        except Exception as e:
            logger.critical("Hmmmm, no luck", exc_info=e)

        self.qWait()
        self.assertEqual(widget.logCount(), 1)

        model = widget.model()
        index = model.index(0, 0)
        assert model.rowCount(index) == 1
        index = model.index(0, 0, index)
        assert model.rowCount(index) == 1
        index = model.index(0, 0, index)
        assert model.rowCount(index) == 1
        index = model.index(0, 0, index)
        assert model.rowCount(index) == 0
        widget = None
