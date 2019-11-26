# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Module defining the main entry of the Flint modelization.
"""
from __future__ import annotations
from typing import List

from silx.gui import qt

from . import scan_model
from . import plot_model


class Workspace(qt.QObject):

    plotAdded = qt.Signal(object)
    plotRemoved = qt.Signal(object)
    widgetAdded = qt.Signal(object)
    widgetRemoved = qt.Signal(object)

    def __init__(self, parent=None):
        super(Workspace, self).__init__(parent=parent)
        self.__plots: List[plot_model.Plot] = []
        self.__widgets: List[qt.QWidget] = []

    def plots(self) -> List[plot_model.Plot]:
        return self.__plots

    def addPlot(self, plot):
        self.__plots.append(plot)
        self.plotAdded.emit(plot)

    def removePlot(self, plot):
        self.__plots.remove(plot)
        self.plotRemoved.emit(plot)

    def widgets(self) -> List[qt.QWidget]:
        return self.__widgets

    def addWidget(self, widget):
        self.__widgets.append(widget)
        self.widgetAdded.emit(widget)

    def removeWidget(self, widget):
        self.__widgets.remove(widget)
        self.widgetRemoved.emit(widget)

    def popWidgets(self) -> List[qt.QWidget]:
        widgets = list(self.__widgets)
        self.__widgets = []
        for widget in widgets:
            self.widgetRemoved.emit(widget)
        return widgets

    def clearWidgets(self):
        widgets = list(self.__widgets)
        self.__widgets = []
        for widget in widgets:
            self.widgetRemoved.emit(widget)


class FlintState(qt.QObject):

    currentScanChanged = qt.Signal(object, object)

    workspaceChanged = qt.Signal(object, object)

    blissSessionChanged = qt.Signal()

    def __init__(self, parent=None):
        super(FlintState, self).__init__(parent=parent)
        self.__workspace: Workspace = None
        self.__currentScan: scan_model.Scan = None
        # FIXME: widget should be weakref
        self.__liveWindow = None
        self.__propertyWidget = None
        self.__liveStatusWidget = None
        self.__manager = None
        self.__flintApi = None
        self.__settings = None
        self.__mainWindow = None
        self.__scanManager = None
        self.__blissSessionName = None
        self.__redisConnection = None

    def setSettings(self, settings: qt.QSettings):
        self.__settings = settings

    def settings(self) -> qt.QSettings:
        return self.__settings

    def setBlissSessionName(self, sessionName: str):
        self.__blissSessionName = sessionName
        self.blissSessionChanged.emit()

    def blissSessionName(self) -> str:
        return self.__blissSessionName

    def setRedisConnection(self, redisConnection):
        self.__redisConnection = redisConnection

    def redisConnection(self):
        return self.__redisConnection

    def setMainWindow(self, mainWindow: qt.QMainWindow):
        self.__mainWindow = mainWindow

    def mainWindow(self) -> qt.QMainWindow:
        return self.__mainWindow

    def setMainManager(self, manager):
        self.__manager = manager

    def mainManager(self):
        return self.__manager

    def setScanManager(self, manager):
        self.__scanManager = manager

    def scanManager(self):
        return self.__scanManager

    def setLiveWindow(self, window: qt.QMainWindow):
        self.__liveWindow = window

    def liveWindow(self) -> qt.QMainWindow:
        return self.__liveWindow

    def setLiveStatusWidget(self, widget: qt.QWidget):
        self.__liveStatusWidget = widget

    def liveStatusWidget(self) -> qt.QWidget:
        return self.__liveStatusWidget

    def setFlintApi(self, flintApi):
        self.__flintApi = flintApi

    def flintApi(self):
        return self.__flintApi

    def setPropertyWidget(self, propertyWidget: qt.QWidget):
        propertyWidget.setObjectName("property-widget")
        self.__propertyWidget = propertyWidget

    def propertyWidget(self) -> qt.QWidget:
        return self.__propertyWidget

    def setWorkspace(self, workspace: Workspace):
        previous = self.__workspace
        self.__workspace: Workspace = workspace
        self.workspaceChanged.emit(previous, workspace)

    def workspace(self) -> Workspace:
        return self.__workspace

    def setCurrentScan(self, scan: scan_model.Scan):
        if not scan.isSealed():
            raise scan_model.SealedError("Must be sealed, explicitly")
        previous = self.__currentScan
        self.__currentScan = scan
        self.currentScanChanged.emit(previous, scan)

    def currentScan(self) -> scan_model.Scan:
        return self.__currentScan
