# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging

from silx.gui import qt
from bliss.flint.model import flint_model
from bliss.flint.widgets.log_widget import LogWidget


class StateIndicator(qt.QWidget):
    """
    Widget to display an indicator when a waning or an error was logged.

    The indicator is reset when the log window is consulted.
    """

    def __init__(self, parent=None):
        super(StateIndicator, self).__init__(parent=parent)
        self.__action = qt.QAction(self)

        self.__button = qt.QToolBar(self)
        self.__button.setIconSize(qt.QSize(10, 10))
        self.__button.addAction(self.__action)
        self.__action.triggered.connect(self.__clicked)
        self.__action.setEnabled(False)

        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.__button)
        self.__model: flint_model.FlintState = None
        self.__logWidget: LogWidget = None
        self.__lastLevelNo: int = 0

    def __clicked(self):
        flintWindow = self.__model.mainWindow()
        flintWindow.showLogDialog()

    def setFlintModel(self, model: flint_model.FlintState):
        self.__model = model

    def setLogWidget(self, logWidget: LogWidget):
        logWidget.logEmitted.connect(self.__logEmitted)
        logWidget.activated.connect(self.__logWidgetActivated)
        self.__logWidget = logWidget

    def __createCircleIcon(self, color: qt.QColor):
        pixmap = qt.QPixmap(10, 10)
        pixmap.fill(qt.Qt.transparent)
        painter = qt.QPainter(pixmap)
        painter.setRenderHint(qt.QPainter.Antialiasing)
        painter.setPen(color)
        painter.setBrush(qt.QBrush(color))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()
        return qt.QIcon(pixmap)

    def __logEmitted(self, levelno: int):
        if levelno <= self.__lastLevelNo:
            return
        if levelno < logging.WARNING:
            return
        if self.__logWidget.isActiveWindow():
            return
        self.__lastLevelNo = levelno
        color = self.__logWidget.colorFromLevel(levelno)
        icon = self.__createCircleIcon(color)
        self.__action.setIcon(icon)
        self.__action.setEnabled(True)
        self.__action.setToolTip("Unread logging messages")

    def __logWidgetActivated(self):
        self.__lastLevelNo = 0
        self.__action.setIcon(qt.QIcon())
        self.__action.setEnabled(False)
        self.__action.setToolTip("")
