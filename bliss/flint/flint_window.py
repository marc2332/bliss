# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Module containing the description of the main window provided by Flint"""

from __future__ import annotations
from typing import Dict

import logging
import os

import silx
from silx.gui import qt

from bliss.flint.widgets.log_widget import LogWidget
from bliss.flint.widgets.live_window import LiveWindow
from bliss.flint.widgets.custom_plot import CustomPlot
from bliss.flint.widgets.state_indicator import StateIndicator
from bliss.flint.widgets.utils import app_actions
from bliss.flint.model import flint_model

_logger = logging.getLogger(__name__)


class FlintWindow(qt.QMainWindow):
    """"Main Flint window"""

    def __init__(self, parent=None):
        qt.QMainWindow.__init__(self, parent=parent)
        self.setAttribute(qt.Qt.WA_QuitOnClose, True)

        self.__flintState: flint_model.FlintState = None
        self.__stateIndicator: StateIndicator = None
        self.__customPlots: Dict[object, CustomPlot] = {}

        central_widget = qt.QWidget(self)

        tabs = qt.QTabWidget(central_widget)
        tabs.setTabsClosable(True)
        tabs.tabCloseRequested[int].connect(self.__tabCloseRequested)
        self.__tabs = tabs

        self.setCentralWidget(tabs)
        self.__initLogWindow()

    def setFlintModel(self, flintState: flint_model.FlintState):
        if self.__flintState is not None:
            self.__flintState.blissSessionChanged.disconnect(self.__blissSessionChanged)
        self.__flintState = flintState
        if self.__flintState is not None:
            self.__flintState.blissSessionChanged.connect(self.__blissSessionChanged)
        self.__updateTitle()
        if self.__stateIndicator is not None:
            self.__stateIndicator.setFlintModel(flintState)

    def flintModel(self) -> flint_model.FlintState:
        assert self.__flintState is not None
        return self.__flintState

    def tabs(self):
        # FIXME: Have to be removed as it is not really an abstraction
        return self.__tabs

    def __tabCloseRequested(self, tabIndex):
        widget = self.__tabs.widget(tabIndex)
        if isinstance(widget, CustomPlot):
            plotId = widget.plotId()
            self.removeCustomPlot(plotId)

    def __initLogWindow(self):
        logWindow = qt.QDialog(self)
        logWidget = LogWidget(logWindow)
        qt.QVBoxLayout(logWindow)
        logWindow.layout().addWidget(logWidget)
        logWindow.setAttribute(qt.Qt.WA_QuitOnClose, False)
        logWindow.setWindowTitle("Log messages")
        logWindow.rejected.connect(self.__saveLogWindowSettings)
        self.__logWindow = logWindow
        self.__logWidget = logWidget
        logWidget.connect_logger(logging.root)

    def initMenus(self):
        flintModel = self.flintModel()
        liveWindow = flintModel.liveWindow()
        manager = flintModel.mainManager()

        exitAction = qt.QAction("&Exit", self)
        exitAction.setShortcut("Ctrl+Q")
        exitAction.setStatusTip("Exit flint")
        exitAction.triggered.connect(self.close)
        showLogAction = qt.QAction("Show &log", self)
        showLogAction.setStatusTip("Show log window")

        showLogAction.triggered.connect(self.showLogDialog)
        menubar = self.menuBar()
        fileMenu = menubar.addMenu("&File")
        fileMenu.addAction(exitAction)

        windowMenu: qt.QMenu = menubar.addMenu("&Windows")
        windowMenu.addSection("Live scans")
        liveWindow.createWindowActions(windowMenu)
        windowMenu.addSection("Helpers")
        windowMenu.addAction(showLogAction)
        action = qt.QAction("&IPython console", self)
        action.setStatusTip("Show a IPython console (for debug purpose)")
        action.triggered.connect(self.openDebugConsole)
        windowMenu.addAction(action)

        displayMenu: qt.QMenu = menubar.addMenu("Display")
        action = app_actions.OpenGLAction(self)
        displayMenu.addAction(action)
        displayMenu.aboutToShow.connect(action.updateState)

        menubar = self.menuBar()
        layoutMenu = menubar.addMenu("&Layout")
        for action in liveWindow.createLayoutActions(self):
            layoutMenu.addAction(action)

        menubar = self.menuBar()
        workspaceMenu = menubar.addMenu("&Workspace")
        workspaceManager = manager.workspaceManager()
        for action in workspaceManager.createManagerActions(self):
            workspaceMenu.addAction(action)

        BLISS_HELP_ROOT = "https://bliss.gitlab-pages.esrf.fr/bliss/master/"
        BLISS_HELP_URL = BLISS_HELP_ROOT
        FLINT_DEMO_URL = BLISS_HELP_ROOT + "bliss_flint.html"
        FLINT_HELP_URL = BLISS_HELP_ROOT + "flint/flint_scan_plotting.html"

        def openUrl(url):
            qt.QDesktopServices.openUrl(qt.QUrl(url))

        helpMenu = menubar.addMenu("&Help")

        action = qt.QAction("Flint online &demo", self)
        action.setStatusTip("Show the online demo about Flint")
        action.triggered.connect(lambda: openUrl(FLINT_DEMO_URL))
        helpMenu.addAction(action)

        helpMenu.addSeparator()

        action = qt.QAction("&BLISS online help", self)
        action.setStatusTip("Show the online help about BLISS")
        action.triggered.connect(lambda: openUrl(BLISS_HELP_URL))
        helpMenu.addAction(action)

        action = qt.QAction("&Flint online help", self)
        action.setStatusTip("Show the online help about Flint")
        action.triggered.connect(lambda: openUrl(FLINT_HELP_URL))
        helpMenu.addAction(action)

        helpMenu.addSeparator()

        action = qt.QAction("&About", self)
        action.setStatusTip("Show the application's About box")
        action.triggered.connect(self.showAboutBox)
        helpMenu.addAction(action)

        stateIndicator = StateIndicator(self)
        stateIndicator.setLogWidget(self.__logWidget)
        stateIndicator.setFlintModel(self.__flintState)
        # widgetAction = qt.QWidgetAction(menubar)
        # widgetAction.setDefaultWidget(stateIndicator)
        # menubar.addAction(widgetAction)
        self.__stateIndicator = stateIndicator
        menubar.setCornerWidget(stateIndicator, qt.Qt.TopLeftCorner)
        # self.__tabs.setCornerWidget(stateIndicator)

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
        self.__initLogWindowFromSettings()

    def showAboutBox(self):
        """Show the about box of Flint"""
        from .widgets.about import About

        About.about(self, "Flint")

    def setFocusOnLiveScan(self):
        self.__tabs.setCurrentIndex(0)

    def setFocusOnPlot(self, plot: qt.QWidget):
        i = self.__tabs.indexOf(plot)
        if i >= 0:
            self.__tabs.setCurrentIndex(i)

    def createTab(self, label, widgetClass=qt.QWidget, closeable=False, selected=False):
        # FIXME: The parent have to be set
        widget = widgetClass()
        index = self.__tabs.addTab(widget, label)
        if selected:
            self.__tabs.setCurrentIndex(index)
        if not closeable:
            closeButton = self.__tabs.tabBar().tabButton(index, qt.QTabBar.RightSide)
            if closeButton is not None:
                closeButton.setVisible(False)
        return widget

    def removeTab(self, widget):
        index = self.__tabs.indexOf(widget)
        self.__tabs.removeTab(index)

    def createLiveWindow(self):
        window: qt.QMainWindow = self.createTab("Live scan", LiveWindow)
        window.setObjectName("scan-window")
        return window

    def __blissSessionChanged(self):
        self.__updateTitle()

    def __updateTitle(self):
        sessionName = self.__flintState.blissSessionName()

        if sessionName is None:
            session = "no session attached."
        else:
            session = "attached to '%s'" % sessionName
        title = "Flint (PID={}) - {}".format(os.getpid(), session)
        self.setWindowTitle(title)

    def __screenId(self):
        """Try to return a kind of unique name to define the used screens.

        This allows to store different preferences for different environements,
        which is the case when we use SSH.
        """
        app = qt.QApplication.instance()
        desktop = app.desktop()
        size = desktop.size()
        return hash(size.width()) ^ hash(size.height())

    def initFromSettings(self):
        settings = self.__flintState.settings()
        # resize window to 70% of available screen space, if no settings
        screenId = self.__screenId()
        groups = settings.childGroups()
        mainWindowGroup = "main-window-%s" % screenId
        if mainWindowGroup not in groups:
            mainWindowGroup = "main-window"
        settings.beginGroup(mainWindowGroup)
        pos = qt.QDesktopWidget().availableGeometry(self).size() * 0.7
        w = pos.width()
        h = pos.height()
        self.resize(settings.value("size", qt.QSize(w, h)))
        self.move(settings.value("pos", qt.QPoint(3 * w / 14.0, 3 * h / 14.0)))
        settings.endGroup()

    def saveToSettings(self):
        settings = self.__flintState.settings()
        screenId = self.__screenId()
        settings.beginGroup("main-window-%s" % screenId)
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()

    def __initLogWindowFromSettings(self):
        settings = self.__flintState.settings()
        # resize window to 70% of available screen space, if no settings
        settings.beginGroup("log-window")
        if settings.contains("size"):
            self.__logWindow.resize(settings.value("size"))
        if settings.contains("pos"):
            self.__logWindow.move(settings.value("pos"))
        settings.endGroup()

    def __saveLogWindowSettings(self):
        settings = self.__flintState.settings()
        settings.beginGroup("log-window")
        settings.setValue("size", self.__logWindow.size())
        settings.setValue("pos", self.__logWindow.pos())
        settings.endGroup()

    def createCustomPlot(self, plotWidget, name, plot_id, selected, closeable):
        """Create a custom plot"""
        customPlot = self.createTab(
            name, widgetClass=CustomPlot, selected=selected, closeable=closeable
        )
        customPlot.setPlotId(plot_id)
        customPlot.setName(name)
        customPlot.setPlot(plotWidget)
        self.__customPlots[plot_id] = customPlot
        plotWidget.show()

    def removeCustomPlot(self, plot_id):
        """Remove a custom plot by its id"""
        customPlot = self.__customPlots.pop(plot_id)
        self.removeTab(customPlot)

    def customPlot(self, plot_id) -> CustomPlot:
        """If the plot does not exist, returns None"""
        plot = self.__customPlots.get(plot_id)
        return plot
