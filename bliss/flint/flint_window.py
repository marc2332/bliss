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
from bliss.flint.widgets.live_window import LiveWindow
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
        tabs.setTabsClosable(True)
        tabs.tabCloseRequested[int].connect(self.__tabCloseRequested)
        self.__tabs = tabs

        self.setCentralWidget(tabs)
        self.__initMenus()
        self.__initLogWindow()

    def setFlintModel(self, flintState: flint_model.FlintState):
        if self.__flintState is not None:
            self.__flintState.blissSessionChanged.disconnect(self.__blissSessionChanged)
        self.__flintState = flintState
        if self.__flintState is not None:
            self.__flintState.blissSessionChanged.connect(self.__blissSessionChanged)
        self.__updateTitle()

    def flintModel(self) -> flint_model.FlintState:
        assert self.__flintState is not None
        return self.__flintState

    def tabs(self):
        # FIXME: Have to be removed as it is not really an abstraction
        return self.__tabs

    def __tabCloseRequested(self, tabIndex):
        new_tab_widget = self.__tabs.widget(tabIndex)
        # FIXME: CustomPlot should not be a flint_api concept
        # FIXME: There should not be a link to flint_api
        plot_id = new_tab_widget._plot_id
        flintApi = self.__flintState.flintApi()
        flintApi.remove_plot(plot_id)

    def __initLogWindow(self):
        logWindow = qt.QDialog(self)
        logWidget = LogWidget(logWindow)
        qt.QVBoxLayout(logWindow)
        logWindow.layout().addWidget(logWidget)
        logWindow.setAttribute(qt.Qt.WA_QuitOnClose, False)
        logWindow.setWindowTitle("Log messages")
        logWindow.rejected.connect(self.__saveLogWindowSettings)
        self.__logWindow = logWindow
        logWidget.connect_logger(logging.root)

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

        menubar = self.menuBar()
        layoutMenu = menubar.addMenu("&Layout")
        self.__layoutMenu = layoutMenu

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
        self.setVisible(True)
        return window

    def updateGui(self):
        flintModel = self.flintModel()
        liveWindow = flintModel.liveWindow()
        layoutMenu = self.__layoutMenu
        for action in liveWindow.createLayoutActions(self):
            layoutMenu.addAction(action)

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

    def saveToSettings(self):
        settings = self.__flintState.settings()
        settings.beginGroup("main-window")
        settings.setValue("size", self.size())
        settings.setValue("pos", self.pos())
        settings.endGroup()

        manager = self.__flintState.mainManager()
        try:
            manager.saveWorkspace()
            _logger.info("Workspace saved")
        except Exception:
            _logger.error("Error while saving the workspace", exc_info=True)

        settings.sync()

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
