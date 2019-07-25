# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide a widget to display logs from `logging` Python  module.
"""

import logging
import warnings


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from silx.gui import qt


class _QtLogHandler(logging.Handler):
    def __init__(self, log_widget):
        logging.Handler.__init__(self)

        self.log_widget = log_widget

    def emit(self, record):
        record = self.format(record)
        # FIXME: widget should be a weakref, or the widget should remove the
        #        handler on destroy
        self.log_widget.appendPlainText(record)
        # FIXME: Add something to avoid logs to grow up to infinit
        # FIXME: A signal should be used, as the handler is not always
        #        the Qt thread

class LogWidget(qt.QPlainTextEdit):

    def __init__(self, parent=None):
        super(LogWidget, self).__init__(parent=parent)
        self.setReadOnly(True)

    def connect_logger(self, logger):
        """
        Connect the widget to a specific logger.
        """
        handler = _QtLogHandler(self)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s: %(message)s"))
        logger.addHandler(handler)
