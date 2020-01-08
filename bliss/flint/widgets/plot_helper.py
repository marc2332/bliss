# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import NamedTuple

import contextlib

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot import PlotWindow
from silx.gui.plot.actions import PlotAction
from silx.gui.plot.actions import control
from silx.gui.plot.actions import io
from silx.gui.plot.tools.profile import ScatterProfileToolBar


class ViewChangedEvent(NamedTuple):
    userInteraction: bool


class MouseMovedEvent(NamedTuple):
    xData: float
    yData: float
    xPixel: int
    yPixel: int


class CheckableKeepAspectRatioAction(PlotAction):
    """QAction controlling X axis log scale on a :class:`.PlotWidget`.

    :param plot: :class:`.PlotWidget` instance on which to operate
    :param parent: See :class:`QAction`
    """

    def __init__(self, plot, parent=None):
        super(CheckableKeepAspectRatioAction, self).__init__(
            plot,
            icon="shape-circle-solid",
            text="Keep aspect ratio",
            tooltip="Keep axes aspect ratio",
            triggered=self._actionTriggered,
            checkable=True,
            parent=parent,
        )
        self.setChecked(self.plot.isKeepDataAspectRatio())
        plot.sigSetKeepDataAspectRatio.connect(self._keepDataAspectRatioChanged)

    def _keepDataAspectRatioChanged(self, aspectRatio):
        """Handle Plot set keep aspect ratio signal"""
        self.setChecked(aspectRatio)

    def _actionTriggered(self, checked=False):
        self.plot.setKeepDataAspectRatio(checked)


class CustomAxisAction(qt.QWidgetAction):
    def __init__(self, plot, parent):
        super(CustomAxisAction, self).__init__(parent)

        menu = qt.QMenu(parent)
        menu.addSection("X-axes")
        action = control.XAxisLogarithmicAction(plot, self)
        action.setText("Log scale")
        menu.addAction(action)

        menu.addSection("Y-axes")
        action = control.YAxisLogarithmicAction(plot, self)
        action.setText("Log scale")
        menu.addAction(action)

        menu.addSection("Aspect ratio")
        action = CheckableKeepAspectRatioAction(plot, self)
        action.setText("Keep aspect ratio")
        menu.addAction(action)

        icon = icons.getQIcon("flint:icons/axes-options")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Custom axis")
        toolButton.setToolTip("Custom the plot axis")
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)


class CustomScatterProfileAction(qt.QWidgetAction):
    def __init__(self, plot, parent):
        super(CustomScatterProfileAction, self).__init__(parent)

        self.__toolbar = ScatterProfileToolBar(parent=parent, plot=plot)
        self.__toolbar.setVisible(False)

        menu = qt.QMenu(parent)
        for action in self.__toolbar.actions():
            menu.addAction(action)

        icon = icons.getQIcon("flint:icons/profile")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Profile tools")
        toolButton.setToolTip(
            "Manage the profiles to this scatter (not yet implemented)"
        )
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)


class ExportOthers(qt.QWidgetAction):
    def __init__(self, plot, parent):
        super(ExportOthers, self).__init__(parent)

        menu = qt.QMenu(parent)
        menu.addAction(io.CopyAction(plot, self))
        menu.addAction(io.PrintAction(plot, self))
        menu.addAction(io.SaveAction(plot, self))

        icon = icons.getQIcon("flint:icons/export-others")
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Other exports")
        toolButton.setToolTip("Various exports")
        toolButton.setIcon(icon)
        toolButton.setMenu(menu)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        self.setDefaultWidget(toolButton)


class FlintPlot(PlotWindow):
    """Helper to provide few other functionalities on top of silx.

    This should be removed and merged into silx.
    """

    sigViewChanged = qt.Signal(ViewChangedEvent)

    sigMouseMoved = qt.Signal(MouseMovedEvent)

    sigMouseLeft = qt.Signal()

    def __init__(self, parent=None, backend=None):
        super(FlintPlot, self).__init__(parent=parent, backend=backend)
        self.sigPlotSignal.connect(self.__limitsChanged)
        self.__userInteraction = True

        toolbars = self.findChildren(qt.QToolBar)
        for tb in toolbars:
            self.removeToolBar(tb)

        if hasattr(self, "centralWidget"):
            self.centralWidget().installEventFilter(self)

    @contextlib.contextmanager
    def userInteraction(self):
        self.__userInteraction = True
        try:
            yield
        finally:
            self.__userInteraction = False

    def eventFilter(self, widget, event):
        if event.type() == qt.QEvent.Leave:
            self.__mouseLeft()
            return True
        return False

    def __mouseLeft(self):
        self.sigMouseLeft.emit()

    def __limitsChanged(self, eventDict):
        if eventDict["event"] == "limitsChanged":
            event1 = ViewChangedEvent(self.__userInteraction)
            self.sigViewChanged.emit(event1)
        elif eventDict["event"] == "mouseMoved":
            event2 = MouseMovedEvent(
                eventDict["x"], eventDict["y"], eventDict["xpixel"], eventDict["ypixel"]
            )
            self.sigMouseMoved.emit(event2)

    def keyPressEvent(self, event):
        with self.userInteraction():
            super(FlintPlot, self).keyPressEvent(event)

    def onMousePress(self, xPixel, yPixel, btn):
        with self.userInteraction():
            super(FlintPlot, self).onMousePress(xPixel, yPixel, btn)

    def onMouseMove(self, xPixel, yPixel):
        with self.userInteraction():
            super(FlintPlot, self).onMouseMove(xPixel, yPixel)

    def onMouseRelease(self, xPixel, yPixel, btn):
        with self.userInteraction():
            super(FlintPlot, self).onMouseRelease(xPixel, yPixel, btn)

    def onMouseWheel(self, xPixel, yPixel, angleInDegrees):
        with self.userInteraction():
            super(FlintPlot, self).onMouseWheel(xPixel, yPixel, angleInDegrees)
