# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import List

import logging
import time
import functools

from silx.gui import qt
from silx.gui import icons
from bliss.flint.utils import signalutils


_logger = logging.getLogger(__name__)


class RefreshManager(qt.QObject):
    """Helper to compute a frame rate"""

    refreshModeChanged = qt.Signal()
    """Signal emitted when the refresh mode was changed"""

    def __init__(self, parent: qt.QWidget):
        super(RefreshManager, self).__init__(parent=parent)
        self.__parent = parent
        self.__lastValues: List[float] = []
        self.__lastUpdate: Optional[float] = None
        self.__aggregator: signalutils.EventAggregator = None

        self.__updater = qt.QTimer(self)
        self.__updater.timeout.connect(self.__update)
        self.__updater.start(500)
        self.__scanProcessing = False

    def scanStarted(self):
        self.__scanProcessing = True
        self.reset()

    def scanFinished(self):
        self.__scanProcessing = False

    def __update(self):
        if self.__aggregator.empty():
            return
        _logger.debug("Update widget")
        if self.__scanProcessing:
            self.update()
        self.__aggregator.flush()

    def setAggregator(self, aggregator):
        self.__aggregator = aggregator

    def __aboutToShowRefreshMode(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        currentRate = self.refreshMode()

        menu.addSection("Refresh rate")
        rates = [1000, 500, 200, 100]
        for rate in rates:
            action = qt.QAction(menu)
            action.setCheckable(True)
            action.setChecked(currentRate == rate)
            action.setText(f"{rate} ms")
            action.setToolTip(f"Set the refresh rate to {rate} ms")
            action.triggered.connect(functools.partial(self.setRefreshMode, rate))
            menu.addAction(action)

        action = qt.QAction(menu)
        action.setCheckable(True)
        action.setChecked(currentRate is None)
        action.setText(f"As fast as possible")
        action.setToolTip(f"The plot is updated when a new data is received")
        action.triggered.connect(functools.partial(self.setRefreshMode, None))
        menu.addAction(action)

        menu.addSection("Mesured rate")
        periode = self.periode()
        if periode is not None:
            periode = round(periode * 1000)
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText(f"{periode} ms")
            action.setToolTip(f"Last mesured rate when scan was precessing")
            menu.addAction(action)

    def createRefreshAction(self, parent: qt.QWidget):
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Max refresh mode")
        menu = qt.QMenu(toolButton)
        menu.aboutToShow.connect(self.__aboutToShowRefreshMode)
        toolButton.setMenu(menu)
        toolButton.setToolTip("Custom and check refresh mode applied")
        icon = icons.getQIcon("flint:icons/refresh")
        toolButton.setIcon(icon)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        action = qt.QWidgetAction(parent)
        action.setDefaultWidget(toolButton)
        return action

    def update(self):
        now = time.time()
        if self.__lastUpdate is not None:
            periode = now - self.__lastUpdate
            self.__lastValues.append(periode)
            self.__lastValues = self.__lastValues[-5:]
        else:
            # Clean up the load values
            self.__lastValues = []

        self.__lastUpdate = now

    def reset(self):
        self.__lastUpdate = None

    def frameRate(self):
        if self.__lastValues == []:
            return None
        return 1 / self.periode()

    def periode(self):
        if self.__lastValues == []:
            return None
        return sum(self.__lastValues) / len(self.__lastValues)

    def refreshMode(self) -> Optional[int]:
        """Returns the current mode used by this manager.

        It can be None when there is no delay, or a number in millisecond
        for the refresh rate used.
        """
        if self.__updater.isActive():
            return self.__updater.interval()
        else:
            return None

    def setRefreshMode(self, rate: Optional[int]):
        """Set the refresh mode to use with this manager.

        It can be None when there is no delay, or a number in millisecond
        for the refresh rate used.
        """
        if rate is None:
            if self.__updater.isActive():
                self.__updater.stop()
                self.__aggregator.eventAdded.connect(
                    self.__update, qt.Qt.QueuedConnection
                )
        else:
            if self.__updater.isActive():
                self.__updater.setInterval(rate)
            else:
                self.__updater.start(rate)
                self.__aggregator.eventAdded.disconnect(self.__update)
        self.refreshModeChanged.emit()
