# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from silx.gui import qt
from bliss.flint.widgets.curve_plot import CurvePlotWidget


class LiveWindow(qt.QMainWindow):
    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self, parent=parent)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            self.dockOptions()
            | qt.QMainWindow.AllowNestedDocks
            | qt.QMainWindow.AllowTabbedDocks
            | qt.QMainWindow.GroupedDragging
            | qt.QMainWindow.AnimatedDocks
            # | qt.QMainWindow.VerticalTabs
        )

        self.tabifiedDockWidgetActivated.connect(self.__tabActivated)

    def __tabActivated(self, dock: qt.QDockWidget):
        if hasattr(dock, "widgetActivated"):
            dock.widgetActivated.emit(dock)

    def feedDefaultWorkspace(self, flintModel, workspace):
        curvePlotWidget = CurvePlotWidget(parent=self)
        curvePlotWidget.setFlintModel(flintModel)
        curvePlotWidget.setObjectName("curve1-dock")
        curvePlotWidget.setWindowTitle("Curve1")
        curvePlotWidget.setFeatures(
            curvePlotWidget.features() & ~qt.QDockWidget.DockWidgetClosable
        )
        curvePlotWidget.widget().setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        workspace.addWidget(curvePlotWidget)
        self.addDockWidget(qt.Qt.RightDockWidgetArea, curvePlotWidget)
