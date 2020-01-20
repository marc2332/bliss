# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import NamedTuple
from typing import Optional

import contextlib
import numpy
import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot import PlotWindow
from silx.gui.plot.actions import PlotAction
from silx.gui.plot.actions import control
from silx.gui.plot.actions import io
from silx.gui.plot.tools.profile import ScatterProfileToolBar
from silx.gui.plot.items.marker import Marker
from silx.gui.plot.items.scatter import Scatter

from bliss.flint.model import plot_model


_logger = logging.getLogger(__name__)


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
        action = control.YAxisInvertedAction(plot, self)
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


class _FlintItemMixIn:
    def __init__(self):
        self.__plotItem = None

    def customItem(self) -> Optional[plot_model.Item]:
        return self.__plotItem

    def setCustomItem(self, item: plot_model.Item):
        self.__plotItem = item


class FlintScatter(Scatter, _FlintItemMixIn):
    def __init__(self):
        Scatter.__init__(self)
        _FlintItemMixIn.__init__(self)


class TooltipItemManager:
    def __init__(self, parent: qt.QWidget, plot: FlintPlot):
        self.__parent = parent

        self.__toolTipMarker = Marker()
        self.__toolTipMarker._setLegend("marker-tooltip")
        self.__toolTipMarker.setColor("pink")
        self.__toolTipMarker.setSymbol("+")
        self.__toolTipMarker.setSymbolSize(8)
        self.__toolTipMarker.setVisible(False)

        self.__plot = plot

        plot.sigMouseMoved.connect(self.__onMouseMove)
        plot.sigMouseLeft.connect(self.__onMouseLeft)

    def setFilter(self, filterClass):
        self.__filterClass = filterClass

    def marker(self):
        return self.__toolTipMarker

    def __onMouseMove(self, event: MouseMovedEvent):
        mouseButton = qt.QApplication.mouseButtons()
        mode = self.__plot.getInteractiveMode()
        if mouseButton == qt.Qt.NoButton and mode["mode"] in ["zoom", "pan"]:
            self.__updateTooltip(event.xPixel, event.yPixel)
        else:
            # Avoid to display the tooltip if the user is doing stuffs
            self.__updateTooltip(None, None)

    def __onMouseLeft(self):
        self.__updateTooltip(None, None)

    def __updateTooltip(self, x, y):
        plot = self.__plot

        # Start from top-most item
        result = None
        if x is not None:
            for result in plot.pickItems(
                x, y, lambda item: isinstance(item, self.__filterClass)
            ):
                # Break at the first result
                break

        if result is not None:
            # Get last index
            # with matplotlib it should be the top-most point
            index = result.getIndices(copy=False)[-1]
            item = result.getItem()
            if isinstance(item, FlintScatter):
                x, y, text = self.__createScatterTooltip(item, index)
                self.__updateToolTipMarker(x, y)
                cursorPos = qt.QCursor.pos() + qt.QPoint(10, 10)
                qt.QToolTip.showText(cursorPos, text, self.__plot)
            else:
                _logger.error("Unsupported class %s", type(item))
                self.__updateToolTipMarker(None, None)
                qt.QToolTip.hideText()
        else:
            self.__updateToolTipMarker(None, None)
            qt.QToolTip.hideText()

    def __createScatterTooltip(self, item: FlintScatter, index: int):
        x = item.getXData(copy=False)[index]
        y = item.getYData(copy=False)[index]
        value = item.getValueData(copy=False)[index]

        assert isinstance(item, _FlintItemMixIn)
        plotItem = item.customItem()
        if plotItem is not None:
            assert (
                plotItem.xChannel() is not None
                and plotItem.yChannel() is not None
                and plotItem.valueChannel() is not None
            )
            scan = self.__parent.scan()
            xName = plotItem.xChannel().displayName(scan)
            yName = plotItem.yChannel().displayName(scan)
            vName = plotItem.valueChannel().displayName(scan)
        else:
            xName = "X"
            yName = "Y"
            vName = "Value"

        colormap = item.getColormap()
        # FIXME silx 0.13 provides a better API for that
        vmin, vmax = colormap.getColormapRange(item.getValueData(copy=False))
        colors = colormap.applyToData(numpy.array([value, vmin, vmax]))
        cssColor = f"#{colors[0,0]:02X}{colors[0,1]:02X}{colors[0,2]:02X}"

        flintModel = self.__parent.flintModel()

        if flintModel is not None and flintModel.getDate() == "0214":
            char = "\u2665"
        else:
            char = "■"

        text = f"""<html><ul>
        <li><b>Index:</b> {index}</li>
        <li><b>{xName}:</b> {x}</li>
        <li><b>{yName}:</b> {y}</li>
        <li><b>{vName}:</b> <font color="{cssColor}">{char}</font> {value}</li>
        </ul></html>"""
        return x, y, text

    def __updateToolTipMarker(self, x, y):
        if x is None:
            self.__toolTipMarker.setVisible(False)
        else:
            self.__toolTipMarker.setVisible(True)
            self.__toolTipMarker.setPosition(x, y)
