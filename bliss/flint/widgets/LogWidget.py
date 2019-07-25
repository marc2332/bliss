# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide a widget to display logs from `logging` Python module.
"""

import logging
import functools
import warnings
import weakref


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import qt


class _QtLogHandler(logging.Handler):
    def __init__(self, log_widget):
        logging.Handler.__init__(self)
        self._log_widget = weakref.ref(log_widget)

    def get_log_widget(self):
        """
        Returns the log widget connected to this handler.

        The result can be None.
        """
        return self._log_widget()

    def emit(self, record):
        record = self.format(record)
        widget = self.get_log_widget()
        if widget is not None:
            # FIXME: Add something to avoid logs to grow up to infinit
            # FIXME: A signal should be used, as the handler is not always
            #        the Qt thread
            widget.appendPlainText(record)


class LogWidget(qt.QPlainTextEdit):

    def __init__(self, parent=None):
        super(LogWidget, self).__init__(parent=parent)
        self.setReadOnly(True)
        self._handlers = weakref.WeakKeyDictionary()
        self.destroyed.connect(functools.partial(self._remove_handlers, self._handlers))

    @staticmethod
    def _remove_handlers(handlers):
        # NOTE: This function have to be static to avoid cyclic reference to the widget
        #       in the destroyed signal
        for handler, logger in handlers.items():
            logger.removeHandler(handler)
        handlers.clear()

    def connect_logger(self, logger):
        """
        Connect the widget to a specific logger.
        """
        handler = _QtLogHandler(self)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s: %(message)s"))
        logger.addHandler(handler)
        self._handlers[handler] = logger
