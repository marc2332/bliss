# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

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
        self.__plots = []
        self.__widgets = []

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
        widgets = self.__widgets
        self.__widgets = []
        return widgets

    def clearWidgets(self):
        self.__widgets = []


class FlintState(qt.QObject):

    currentScanChanged = qt.Signal(object, object)

    workspaceChanged = qt.Signal(object, object)

    def __init__(self, parent=None):
        super(FlintState, self).__init__(parent=parent)
        self.__workspace = Workspace(self)
        self.__currentScan = None
        self.__window = None

    def setWindow(self, window: qt.QMainWindow):
        self.__window = window

    def window(self) -> qt.QMainWindow:
        return self.__window

    def setWorkspace(self, workspace: Workspace):
        previous = self.__workspace
        self.__workspace = workspace
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
