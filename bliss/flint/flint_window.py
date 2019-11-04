# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Module containing the description of the main window provided by Flint"""

import logging
import os

from silx.gui import qt

from bliss.flint.widgets.log_widget import LogWidget
from bliss.flint.widgets.curve_plot import CurvePlotWidget
from bliss.flint.model import flint_model

_logger = logging.getLogger(__name__)


class FlintWindow(qt.QMainWindow):
    """"Main Flint window"""

    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self, parent=parent)
        self.setAttribute(qt.Qt.WA_QuitOnClose, True)

        self.__flintState: flint_model.FlintState = None

        central_widget = qt.QWidget(self)

        tabs = qt.QTabWidget(central_widget)
        self.__tabs = tabs

        self.setCentralWidget(tabs)
        self.__initMenus()
        self.__initLogWindow()

    def setFlintState(self, flintState):
        if self.__flintState is not None:
            self.__flintState.blissSessionChanged.disconnect(self.__blissSessionChanged)
        self.__flintState = flintState
        if self.__flintState is not None:
            self.__flintState.blissSessionChanged.connect(self.__blissSessionChanged)
        self.__updateTitle()

    def tabs(self):
        # FIXME: Have to be removed as it is not really an abstraction
        return self.__tabs

    def __initLogWindow(self):
        logWindow = qt.QDialog(self)
        logWidget = LogWidget(logWindow)
        qt.QVBoxLayout(logWindow)
        logWindow.layout().addWidget(logWidget)
        logWindow.setAttribute(qt.Qt.WA_QuitOnClose, False)
        logWindow.setWindowTitle("Log messages")
        self.__logWindow = logWindow
        logWidget.connect_logger(_logger)

    def __initMenus(self):
        exitAction = qt.QAction("&Exit", self)
        exitAction.setShortcut("Ctrl+Q")
        exitAction.setStatusTip("Exit flint")
        exitAction.triggered.connect(self.close)
        showLogAction = qt.QAction("Show &log", self)
        showLogAction.setShortcut("Ctrl+L")
        showLogAction.setStatusTip("Show log window")

        showLogAction.triggered.connect(self.showLogDialog)
        menubar = self.menuBar()
        fileMenu = menubar.addMenu("&File")
        fileMenu.addAction(exitAction)
        windowMenu = menubar.addMenu("&Windows")
        windowMenu.addAction(showLogAction)

        helpMenu = menubar.addMenu("&Help")

        action = qt.QAction("&About", self)
        action.setStatusTip("Show the application's About box")
        action.triggered.connect(self.showAboutBox)
        helpMenu.addAction(action)

        action = qt.QAction("&IPython console", self)
        action.setStatusTip("Show a IPython console (for debug purpose)")
        action.triggered.connect(self.openDebugConsole)
        helpMenu.addAction(action)

    def openDebugConsole(self):
        """Open a new debug console"""
        try:
            from silx.gui.console import IPythonDockWidget
        except ImportError:
            _logger.debug("Error while loading IPython console", exc_info=True)
            _logger.error("IPython not available")
            return

        available_vars = {"flintState": self.__flintState, "window": self}
        banner = (
            "The variable 'flintState' and 'window' are available.\n"
            "Use the 'whos' and 'help(flintState)' commands for more information.\n"
            "\n"
        )
        widget = IPythonDockWidget(
            parent=self, available_vars=available_vars, custom_banner=banner
        )
        widget.setAttribute(qt.Qt.WA_DeleteOnClose)
        self.addDockWidget(qt.Qt.RightDockWidgetArea, widget)
        widget.show()

    def showLogDialog(self):
        """Show the log dialog of Flint"""
        self.__logWindow.show()

    def showAboutBox(self):
        """Show the about box of Flint"""
        from .widgets.about import About

        About.about(self, "Flint")

    def createTab(self, label, widgetClass=qt.QWidget):
        # FIXME: The parent have to be set
        widget = widgetClass()
        self.__tabs.addTab(widget, label)
        return widget

    def removeTab(self, widget):
        index = self.__tabs.indexOf(widget)
        self.__tabs.removeTab(index)

    def createLiveWindow(self):
        window: qt.QMainWindow = self.createTab("Live scan", qt.QMainWindow)
        window.setObjectName("scan-window")
        window.setDockNestingEnabled(True)
        window.setDockOptions(
            window.dockOptions()
            | qt.QMainWindow.AllowNestedDocks
            | qt.QMainWindow.AllowTabbedDocks
            | qt.QMainWindow.GroupedDragging
            | qt.QMainWindow.AnimatedDocks
            # | qt.QMainWindow.VerticalTabs
        )
        window.setVisible(True)
        return window

    def __blissSessionChanged(self):
        self.__updateTitle()

    def __updateTitle(self):
        sessionName = self.__flintState.blissSessionName()

        if sessionName is None:
            session = "no session attached."
        else:
            session = "attached to '%s`" % sessionName
        title = "Flint (PID={}) - {}".format(os.getpid(), session)
        self.setWindowTitle(title)

    def __feedDefaultWorkspace(self):
        # FIXME: Here we can feed the workspace with something persistent
        flintModel = self.__flintState
        workspace = flintModel.workspace()
        window = flintModel.liveWindow()

        curvePlotWidget = CurvePlotWidget(parent=window)
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
        window.addDockWidget(qt.Qt.RightDockWidgetArea, curvePlotWidget)

    def initFromSettings(self):
        settings = self.__flintState.settings()
        # resize window to 70% of available screen space, if no settings
        settings.beginGroup("main-window")
        pos = qt.QDesktopWidget().availableGeometry(self).size() * 0.7
        w = pos.width()
        h = pos.height()
        self.resize(settings.value("size", qt.QSize(w, h)))
        self.move(settings.value("pos", qt.QPoint(3 * w / 14.0, 3 * h / 14.0)))
        settings.endGroup()

        manager = self.__flintState.mainManager()
        settings.beginGroup("live-window")
        state = settings.value("workspace", None)
        if state is not None:
            try:
                manager.restoreWorkspace(state)
                _logger.info("Workspace restored")
            except Exception:
                _logger.error("Error while restoring the workspace", exc_info=True)
                self.__feedDefaultWorkspace()
        else:
            self.__feedDefaultWorkspace()
        settings.endGroup()

    def saveToSettings(self):
        settings = self.__flintState.settings()
        settings.beginGroup("main-window")
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()

        manager = self.__flintState.mainManager()
        settings.beginGroup("live-window")
        try:
            state = manager.saveWorkspace(includePlots=False)
            settings.setValue("workspace", state)
            _logger.info("Workspace saved")
        except Exception:
            _logger.error("Error while saving the workspace", exc_info=True)
        settings.endGroup()

        settings.sync()
