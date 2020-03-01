# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional

from silx.gui import qt


class MainWindow(qt.QMainWindow):
    def __init__(self, parent: qt.QWidget = None):
        super(MainWindow, self).__init__(parent=parent)
        self.__locked = False

    def isLayoutLocked(self) -> bool:
        return self.__locked

    def setLayoutLocked(self, locked: bool):
        if self.__locked == locked:
            return
        self.__locked = locked

        docks = self.findChildren(qt.QDockWidget)
        for dock in docks:
            if isinstance(dock, ExtendedDockWidget):
                dock.setLocked(locked)

        # Simplification to search for floating tabbed docks
        floatingWindows = {}
        for dock in docks:
            parent = dock.parent()
            if parent is self:
                continue
            floatingWindows[parent] = floatingWindows.get(parent, 0) + 1
        floatingWindows = [w for (w, count) in floatingWindows.items() if count > 1]

        # Tune the tabbar in order to avoid any move
        # FIXME: Have to be improved
        for dockHolder in [self, *floatingWindows]:
            for tb in dockHolder.children():
                if isinstance(tb, qt.QTabBar):
                    tb.setMovable(not locked)

        for window in floatingWindows:
            window.setWindowFlags(
                qt.Qt.CustomizeWindowHint
                | qt.Qt.WindowCloseButtonHint
                | qt.Qt.WindowTitleHint
                | qt.Qt.WindowSystemMenuHint
                | qt.Qt.Window
                | qt.Qt.Dialog
                | qt.Qt.Popup
            )

    def event(self, event):
        # At the ChildAdded the widget type is not yet known
        if event.type() == qt.QEvent.ChildPolished:
            child = event.child()
            if isinstance(child, ExtendedDockWidget):
                child.setLocked(self.__locked)
        return super(MainWindow, self).event(event)


class ExtendedDockWidget(qt.QDockWidget):

    windowClosed = qt.Signal()

    def __init__(self, parent: Optional[qt.QWidget] = None):
        qt.QDockWidget.__init__(self, parent=parent)
        self.__locked = False
        self.__preventEventLoop = False

        # FIXME: I guess it exists a better way to do that?
        closeButton = self.findChild(qt.QAbstractButton, "qt_dockwidget_closebutton")
        closeButton.clicked.connect(self.__windowClosed)

    def __windowClosed(self):
        self.windowClosed.emit()

    def isLocked(self) -> bool:
        return self.__locked

    def setLocked(self, locked: bool):
        if self.__locked == locked:
            return
        self.__locked = locked
        self.__updateMovable()

    def event(self, event):
        if self.__locked:
            if event.type() == qt.QEvent.NonClientAreaMouseButtonDblClick:
                # Inhibit the double-click on the floating dock when it was locked
                # This behaviour put back the dock to the mainwindows and we don't want that
                # FIXME: Check if this hack also inhibit double click on the client side of the widget
                event.ignore()
                return True

        if event.type() == qt.QEvent.Show:
            if not self.__preventEventLoop:
                self.__updateMovable()

        return super(ExtendedDockWidget, self).event(event)

    def __isFloatingTabbed(self):
        """This widget is part of tabbed dock in a floating window."""
        parent = self.parent()
        return type(parent) == qt.QWidget and parent.windowFlags() & qt.Qt.Dialog

    def __updateMovable(self):
        self.__preventEventLoop = True
        if not self.__locked:
            self.setTitleBarWidget(None)
            features = (
                qt.QDockWidget.DockWidgetMovable
                | qt.QDockWidget.DockWidgetFloatable
                | qt.QDockWidget.DockWidgetClosable
            )
            self.setFeatures(features)
            self.setAllowedAreas(qt.Qt.AllDockWidgetAreas)
        else:
            self.setAllowedAreas(qt.Qt.NoDockWidgetArea)

            if self.isFloating():
                self.setTitleBarWidget(None)
                features = (
                    qt.QDockWidget.DockWidgetMovable
                    | qt.QDockWidget.DockWidgetFloatable
                )
            elif self.__isFloatingTabbed():
                # Avoid strange behaviors but the tool window is still
                # movable inside the main window. See https://bugreports.qt.io/browse/QTBUG-68535
                self.setTitleBarWidget(None)
                features = qt.QDockWidget.DockWidgetMovable
            else:
                dummyTitleBarWidget = qt.QWidget(self)
                self.setTitleBarWidget(dummyTitleBarWidget)
                features = qt.QDockWidget.NoDockWidgetFeatures
            self.setFeatures(features)
        self.__preventEventLoop = False
