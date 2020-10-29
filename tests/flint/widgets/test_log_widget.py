"""Testing LogWidget."""

import logging
import weakref
import pytest
from silx.gui.utils.testutils import TestCaseQt
from bliss.flint.widgets.log_widget import LogWidget

test_logger = logging.getLogger("bliss.tests." + __name__)
test_logger.propagate = False


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
        widget.connect_logger(test_logger)
        self.assertEqual(widget.logCount(), 0)
        test_logger.warning("Tout le %s s'eclate", "monde")
        self.qWait()
        test_logger.error("A la queu%s%s", "leu", "leu")
        self.qWait()
        self.assertEqual(widget.logCount(), 2)
        widget = None

    def test_buggy_logging(self):
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(test_logger)
        self.assertEqual(widget.logCount(), 0)
        test_logger.warning("Two fields expected %s %f", "foo")
        test_logger.warning("Float field expected %f", "foo")
        self.qWait()
        self.assertEqual(widget.logCount(), 2)
        widget = None

    def test_max_logs(self):
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(test_logger)
        widget.setMaximumLogCount(2)
        self.assertEqual(widget.logCount(), 0)
        test_logger.warning("A1")
        test_logger.warning("A1")
        test_logger.warning("B2")
        test_logger.warning("B2")
        self.qWait()
        self.assertEqual(widget.logCount(), 2)

        plainText = self.plain_text(widget)
        self.assertEqual(plainText.count("A1"), 0)
        self.assertEqual(plainText.count("B2"), 2)
        widget = None

    def test_handler_released_on_destroy(self):
        nb = len(test_logger.handlers)
        widget = LogWidget()
        widget.show()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(test_logger)
        self.assertEqual(len(test_logger.handlers), nb + 1)

        ref = weakref.ref(widget)
        widget = None
        self.qWaitForDestroy(ref)

        self.assertEqual(len(test_logger.handlers), nb)

    def test_causes(self):
        """Coverage with exception containing causes"""
        widget = LogWidget()
        self.qWaitForWindowExposed(widget)
        widget.connect_logger(test_logger)

        try:
            try:
                try:
                    raise IndexError("AAA")
                except Exception as e:
                    raise RuntimeError("BBB") from e
            except Exception as e:
                raise RuntimeError("CCC") from e
        except Exception as e:
            test_logger.critical("Hmmmm, no luck", exc_info=e)

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
