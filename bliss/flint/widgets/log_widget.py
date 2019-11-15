# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide a widget to display logs from `logging` Python module.
"""

from __future__ import annotations
from typing import Union
from typing import Optional

import sys
import logging
import functools
import weakref
import traceback

from silx.gui import qt
from silx.gui.utils import concurrent


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
        widget = self.get_log_widget()
        if widget is None:
            return
        try:
            concurrent.submitToQtMainThread(widget.emit, record)
        except Exception:
            self.handleError(record)

    def handleError(self, record):
        t, v, tb = sys.exc_info()
        msg = "%s %s %s" % (t, v, "".join(traceback.format_tb(tb)))
        widget = self.get_log_widget()
        if widget is None:
            return
        concurrent.submitToQtMainThread(widget.emit, msg)


class LogWidget(qt.QTreeView):
    """"Display messages from the Python logging system.

    By default only the 10000 last messages are displayed. This can be customed
    using the method `setMaximumLogCount`
    """

    DateTimeColumn = 0
    LevelColumn = 1
    ModuleNameColumn = 2
    MessageColumn = 3

    def __init__(self, parent=None):
        super(LogWidget, self).__init__(parent=parent)
        self.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self._handlers = weakref.WeakKeyDictionary()
        self.destroyed.connect(functools.partial(self._remove_handlers, self._handlers))
        self._maximumLogCount = 0
        self.setMaximumLogCount(10000)
        self._formatter = logging.Formatter()

        model = qt.QStandardItemModel(self)
        model.setColumnCount(4)
        model.setHorizontalHeaderLabels(["Date/time", "Level", "Module", "Message"])
        self.setModel(model)

        header = self.header()
        header.setSectionResizeMode(
            self.DateTimeColumn, qt.QHeaderView.ResizeToContents
        )
        header.setSectionResizeMode(self.LevelColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(
            self.ModuleNameColumn, qt.QHeaderView.ResizeToContents
        )
        header.setSectionResizeMode(self.MessageColumn, qt.QHeaderView.Stretch)

    @staticmethod
    def _remove_handlers(handlers):
        # NOTE: This function have to be static to avoid cyclic reference to the widget
        #       in the destroyed signal
        for handler, logger in handlers.items():
            logger.removeHandler(handler)
        handlers.clear()

    def setMaximumLogCount(self, maximum):
        self._maximumLogCount = maximum

    def logCount(self):
        """
        Returns the amount of log messages displayed.
        """
        return self.model().rowCount()

    def _colorFromLevel(self, levelno: int):
        if levelno >= logging.CRITICAL:
            return qt.QColor(240, 0, 240)
        elif levelno >= logging.ERROR:
            return qt.QColor(255, 0, 0)
        elif levelno >= logging.WARNING:
            return qt.QColor(180, 180, 0)
        elif levelno >= logging.INFO:
            return qt.QColor(0, 0, 255)
        elif levelno >= logging.DEBUG:
            return qt.QColor(0, 200, 200)
        return qt.QColor(0, 255, 0)

    def _formatStack(self, record: logging.LogRecord):
        s = ""
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            s = record.exc_text
        if record.stack_info:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + self.formatStack(record.stack_info)
        return s

    def emit(self, record: Union[str, logging.LogRecord]):
        record2: Optional[logging.LogRecord] = None
        if isinstance(record, str):
            message = record
        else:
            record2 = record
            message = record.getMessage()

        try:
            if record2 is not None:
                dt = self._formatter.formatTime(record2)
                dateTimeItem = qt.QStandardItem(dt)
                levelItem = qt.QStandardItem(record2.levelname)
                color = self._colorFromLevel(record2.levelno)
                levelItem.setForeground(color)
                nameItem = qt.QStandardItem(record2.name)
                messageItem = qt.QStandardItem(message)

                stack = self._formatStack(record2)
                if stack != "":
                    dateTimeItem.appendRow(
                        [
                            qt.QStandardItem(),
                            qt.QStandardItem(),
                            qt.QStandardItem(),
                            qt.QStandardItem(stack),
                        ]
                    )
            else:
                dateTimeItem = None
        except Exception as e:
            # Make sure everything is fine
            dateTimeItem = None
            sys.excepthook(*sys.exc_info())

        if dateTimeItem is None:
            dateTimeItem = qt.QStandardItem()
            levelItem = qt.QStandardItem("CRITICAL")
            color = self._colorFromLevel(logging.CRITICAL)
            levelItem.setForeground(color)
            nameItem = qt.QStandardItem()
            messageItem = qt.QStandardItem(message)

        model: qt.QStandardItemModel = self.model()
        model.appendRow([dateTimeItem, levelItem, nameItem, messageItem])

        if model.rowCount() > self._maximumLogCount:
            count = model.rowCount() - self._maximumLogCount
            model.removeRows(0, count)

    def connect_logger(self, logger):
        """
        Connect the widget to a specific logger.
        """
        handler = _QtLogHandler(self)
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s: %(message)s")
        )
        logger.addHandler(handler)
        self._handlers[handler] = logger
