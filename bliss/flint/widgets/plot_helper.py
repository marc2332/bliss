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
from silx.gui.plot import PlotWindow


class ViewChangedEvent(NamedTuple):
    userInteraction: bool


class MouseMovedEvent(NamedTuple):
    xData: float
    yData: float
    xPixel: int
    yPixel: int


class FlintPlot(PlotWindow):
    """Helper to provide few other functionalities on top of silx.

    This should be removed and merged into silx.
    """

    sigViewChanged = qt.Signal(ViewChangedEvent)

    sigMouseMoved = qt.Signal(MouseMovedEvent)

    def __init__(self, parent=None, backend=None):
        super(FlintPlot, self).__init__(parent=parent, backend=backend)
        self.sigPlotSignal.connect(self.__limitsChanged)
        self.__userInteraction = True

        toolbars = self.findChildren(qt.QToolBar)
        for tb in toolbars:
            self.removeToolBar(tb)

    @contextlib.contextmanager
    def userInteraction(self):
        self.__userInteraction = True
        try:
            yield
        finally:
            self.__userInteraction = False

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
