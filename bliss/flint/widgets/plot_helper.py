# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import NamedTuple
from typing import Optional
from typing import List
from typing import Tuple

import contextlib
import numpy
import logging
import time
import functools

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot import PlotWindow
from silx.gui.plot.actions import PlotAction
from silx.gui.plot.actions import control
from silx.gui.plot.actions import io
from silx.gui.plot.tools.profile import ScatterProfileToolBar
from silx.gui.plot.Profile import ProfileToolBar
from silx.gui.plot import PlotToolButtons
from silx.gui.plot.items.marker import Marker
from silx.gui.plot.items.scatter import Scatter
from silx.gui.plot.items.curve import Curve
from silx.gui.plot.items.histogram import Histogram
from silx.gui.plot.items.image import ImageData
from silx.gui.plot.items import YAxisMixIn
from silx.gui.plot.items import BoundingRect

from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.model import scan_model
from bliss.flint.utils import signalutils
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget


_logger = logging.getLogger(__name__)


class ViewChangedEvent(NamedTuple):
    userInteraction: bool


class MouseMovedEvent(NamedTuple):
    xData: float
    yData: float
    xPixel: int
    yPixel: int


class PlotEventAggregator(signalutils.EventAggregator):
    def reduce(self, eventStack: List) -> Tuple[List, List]:
        """Override the method to reduce plot refresh by
        removing duplication events.
        """
        result = []
        # Reduce specific channel events
        lastSpecificChannel: Set[object] = set([])
        for event in reversed(eventStack):
            _callback, args, _kwargs = event
            if len(args) == 0:
                result.insert(0, event)
                continue
            e = args[0]
            if not isinstance(e, scan_model.ScanDataUpdateEvent):
                result.insert(0, event)
                continue

            channel = e.selectedChannel()
            if channel is not None:
                if channel in lastSpecificChannel:
                    continue
                else:
                    lastSpecificChannel.add(channel)
            result.insert(0, event)
        return result, []


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
    def __init__(self, plot, parent, kind="any"):
        super(CustomAxisAction, self).__init__(parent)

        menu = qt.QMenu(parent)

        action = control.ShowAxisAction(plot, self)
        action.setText("Show the plot axes")
        menu.addAction(action)

        if kind in ["curve", "scatter"]:
            menu.addSection("X-axes")
            action = control.XAxisLogarithmicAction(plot, self)
            action.setText("Log scale")
            menu.addAction(action)

        menu.addSection("Y-axes")
        if kind in ["curve", "scatter", "mca"]:
            action = control.YAxisLogarithmicAction(plot, self)
            action.setText("Log scale")
            menu.addAction(action)
        if kind in ["scatter", "image"]:
            action = control.YAxisInvertedAction(plot, self)
            menu.addAction(action)

        if kind in ["scatter", "image"]:
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


class CustomImageProfileAction(qt.QWidgetAction):
    def __init__(self, plot, parent):
        super(CustomImageProfileAction, self).__init__(parent)

        self.__toolbar = ProfileToolBar(parent=parent, plot=plot)
        self.__toolbar.setVisible(False)

        menu = qt.QMenu(parent)
        for action in self.__toolbar.actionGroup.actions():
            menu.addAction(action)

        action = qt.QWidgetAction(parent)
        action.setDefaultWidget(self.__toolbar.lineWidthSpinBox)
        menu.addAction(action)

        # Add width spin box to toolbar
        widget = qt.QWidget(parent)
        lineWidthSpinBox = qt.QSpinBox(widget)
        lineWidthSpinBox.setRange(1, 1000)
        lineWidthSpinBox.setValue(1)
        lineWidthSpinBox.valueChanged[int].connect(
            self.__toolbar._lineWidthSpinBoxValueChangedSlot
        )
        layout = qt.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(qt.QLabel("Line width:", widget))
        layout.addWidget(lineWidthSpinBox)
        action = qt.QWidgetAction(parent)
        action.setDefaultWidget(widget)
        menu.addAction(action)

        # Add method to toolbar
        widget = qt.QWidget(parent)
        methodsButton = PlotToolButtons.ProfileOptionToolButton(widget, plot)
        methodsButton.sigMethodChanged.connect(self.__toolbar.setProfileMethod)
        layout = qt.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(qt.QLabel("Method:", widget))
        layout.addWidget(methodsButton)
        action = qt.QWidgetAction(parent)
        action.setDefaultWidget(widget)
        menu.addAction(action)

        menu.addAction(self.__toolbar.clearAction)

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


class PlotWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)
    """Emitted when the plot model displayed by the plot was changed"""

    scanModelUpdated = qt.Signal(object)
    """Emitted when the scan model displayed by the plot was changed"""


class PlotConfiguration:
    """Store a plot configuration for serialization"""

    def __init__(self):
        # Mode
        self.interaction_mode: str = None
        self.refresh_rate: Optional[int, None] = None
        # Axis
        self.x_axis_scale: str = None
        self.y_axis_scale: str = None
        self.y2_axis_scale: str = None
        self.y_axis_inverted: bool = False
        self.y2_axis_inverted: bool = False
        # View
        self.grid_mode: bool = False
        self.axis_displayed: bool = True
        # Tools
        self.crossair_enabled: bool = False
        self.colorbar_displayed: bool = False
        self.profile_widget_displayed: bool = False
        self.roi_widget_displayed: None = False
        self.histogram_widget_displayed: None = False

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        """Inherite the serialization to make sure the object can growup in the
        future"""
        state: Dict[str, Any] = {}
        state.update(self.__dict__)
        return state

    def __setstate__(self, state):
        """Inherite the serialization to make sure the object can growup in the
        future"""
        for k in self.__dict__.keys():
            if k in state:
                v = state.pop(k)
                self.__dict__[k] = v

    def __str__(self):
        return self.__dict__.__str__()


class FlintPlot(PlotWindow):
    """Helper to provide few other functionalities on top of silx.

    This should be removed and merged into silx.
    """

    sigViewChanged = qt.Signal(ViewChangedEvent)

    sigMouseMoved = qt.Signal(MouseMovedEvent)

    sigMouseLeft = qt.Signal()

    sigSelectionChanged = qt.Signal(object, object)
    # FIXME: It have to be provided by silx

    def __init__(self, parent=None, backend=None):
        super(FlintPlot, self).__init__(parent=parent, backend=backend)
        self.sigPlotSignal.connect(self.__plotEvents)
        self.__userInteraction = False
        self.sigActiveCurveChanged.connect(self.__activeCurveChanged)

        toolbars = self.findChildren(qt.QToolBar)
        for tb in toolbars:
            self.removeToolBar(tb)

        if hasattr(self, "centralWidget"):
            self.centralWidget().installEventFilter(self)

    def configuration(self) -> PlotConfiguration:
        """Returns a global configuration of the plot"""
        config = PlotConfiguration()

        mode = self.getInteractiveMode()["mode"]
        if mode not in ("pan", "zoom"):
            mode = None
        config.interaction_mode = mode

        # FIXME: implement it
        config.refresh_rate = None

        # Axis
        axis = self.getXAxis()
        config.x_axis_scale = axis.getScale()
        axis = self.getYAxis()
        config.y_axis_scale = axis.getScale()
        config.y_axis_inverted = axis.isInverted()
        axis = self.getYAxis("right")
        config.y2_axis_scale = axis.getScale()
        config.y2_axis_inverted = axis.isInverted()

        # View
        config.grid_mode = self.getGraphGrid()
        config.axis_displayed = self._isAxesDisplayed()

        # Tools
        config.crossair_enabled = self.getGraphCursor() is not None
        config.colorbar_displayed = self.getColorBarAction().isChecked()
        # FIXME: It would be good to do it
        # config.profile_widget_displayed = None
        # config.roi_widget_displayed = None
        # config.histogram_widget_displayed = None

        return config

    def setConfiguration(self, config: PlotConfiguration):
        mode = config.interaction_mode
        if mode in ("pan", "zoom"):
            self.setInteractiveMode(mode)

        # FIXME: implement it
        # config.refresh_rate

        @contextlib.contextmanager
        def safeApply():
            try:
                yield
            except Exception:
                _logger.error(
                    "Error while applying the plot configuration", exc_info=True
                )

        # Axis
        axis = self.getXAxis()
        with safeApply():
            axis.setScale(config.x_axis_scale)
        axis = self.getYAxis()
        with safeApply():
            axis.setScale(config.y_axis_scale)
        with safeApply():
            axis.setInverted(config.y_axis_inverted)
        axis = self.getYAxis("right")
        with safeApply():
            axis.setScale(config.y2_axis_scale)
        with safeApply():
            axis.setInverted(config.y2_axis_inverted)

        # View
        with safeApply():
            self.setGraphGrid(config.grid_mode)
        with safeApply():
            self.setAxesDisplayed(config.axis_displayed)

        # Tools
        if config.crossair_enabled:
            with safeApply():
                self.setGraphCursor(True)
        if config.colorbar_displayed:
            with safeApply():
                self.getColorBarWidget().setVisible(True)

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

    def __plotEvents(self, eventDict):
        if eventDict["event"] == "limitsChanged":
            event1 = ViewChangedEvent(self.__userInteraction)
            self.sigViewChanged.emit(event1)
        elif eventDict["event"] == "mouseMoved":
            event2 = MouseMovedEvent(
                eventDict["x"], eventDict["y"], eventDict["xpixel"], eventDict["ypixel"]
            )
            self.sigMouseMoved.emit(event2)

    def __activeCurveChanged(self, previous, current):
        # FIXME: This have to be provided by silx in a much better way
        if previous is not None:
            previous = self.getCurve(previous)
        if current is not None:
            current = self.getCurve(current)
        # NOTE: previous and current was swapped
        self.sigSelectionChanged.emit(current, previous)

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

    def getFlintTooltip(
        self, index, flintModel, scan: scan_model.Scan
    ) -> Tuple[int, int, str]:
        return None, None, None

    def _getColoredChar(self, value, data, flintModel):
        colormap = self.getColormap()
        # FIXME silx 0.13 provides a better API for that
        vmin, vmax = colormap.getColormapRange(data)
        data = numpy.array([float(value), vmin, vmax])
        colors = colormap.applyToData(data)
        cssColor = f"#{colors[0,0]:02X}{colors[0,1]:02X}{colors[0,2]:02X}"

        if flintModel is not None and flintModel.getDate() == "0214":
            char = "\u2665"
        else:
            char = "■"
        return f"""<font color="{cssColor}">{char}</font>"""

    def _getColoredSymbol(self, flintModel, scan: scan_model.Scan):
        """Returns a colored HTML char according to the expected plot item style
        """
        plotItem = self.customItem()
        if plotItem is not None:
            style = plotItem.getStyle(scan)
            color = style.lineColor
            cssColor = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
        else:
            cssColor = "#000000"

        if flintModel is not None and flintModel.getDate() == "0214":
            char = "\u2665"
        else:
            char = "⬤"
        return f"""<font color="{cssColor}">{char}</font>"""


class FlintScatter(Scatter, _FlintItemMixIn):
    def __init__(self):
        Scatter.__init__(self)
        _FlintItemMixIn.__init__(self)

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        # Drop other picked indexes
        x = self.getXData(copy=False)[index]
        y = self.getYData(copy=False)[index]
        value = self.getValueData(copy=False)[index]

        plotItem = self.customItem()
        if plotItem is not None:
            assert (
                plotItem.xChannel() is not None
                and plotItem.yChannel() is not None
                and plotItem.valueChannel() is not None
            )
            xName = plotItem.xChannel().displayName(scan)
            yName = plotItem.yChannel().displayName(scan)
            vName = plotItem.valueChannel().displayName(scan)
        else:
            xName = "X"
            yName = "Y"
            vName = "Value"

        data = self.getValueData(copy=False)
        char = self._getColoredChar(value, data, flintModel)

        text = f"""
            <li><b>Index:</b> {index}</li>
            <li><b>{xName}:</b> {x}</li>
            <li><b>{yName}:</b> {y}</li>
            <li><b>{vName}:</b> {char} {value}</li>
        """
        return x, y, text


class FlintCurve(Curve, _FlintItemMixIn):
    def __init__(self):
        Curve.__init__(self)
        _FlintItemMixIn.__init__(self)

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        xx = self.getXData(copy=False)
        yy = self.getYData(copy=False)
        xValue = xx[index]
        yValue = yy[index]

        plotItem = self.customItem()
        if isinstance(plotItem, plot_item_model.CurveMixIn):
            xName = plotItem.displayName("x", scan)
            yName = plotItem.displayName("y", scan)
        else:
            plotItem = None
            xName = "X"
            yName = "Y"

        char = self._getColoredSymbol(flintModel, scan)

        text = f"""
        <li style="white-space:pre">{char} <b>{yName}:</b> {yValue} (index {index})</li>
        <li style="white-space:pre">     <b>{xName}:</b> {xValue}</li>
        """

        if isinstance(plotItem, plot_state_model.GaussianFitItem):
            result = plotItem.reachResult(scan)
            if result is not None:
                text += f"""
                <li style="white-space:pre">     <b>std dev (σ):</b> {result.fit.std}</li>
                <li style="white-space:pre">     <b>position (μ):</b> {result.fit.pos_x}</li>
                """

        return xValue, yValue, text


class FlintRawMca(Histogram, _FlintItemMixIn):
    def __init__(self):
        Histogram.__init__(self)
        _FlintItemMixIn.__init__(self)

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        value = self.getValueData(copy=False)[index]
        plotItem = self.customItem()
        if plotItem is not None:
            assert plotItem.mcaChannel() is not None
            mcaName = plotItem.mcaChannel().displayName(scan)
        else:
            plotItem = None
            mcaName = "MCA"

        char = self._getColoredSymbol(flintModel, scan)

        text = f"""<li style="white-space:pre">{char} <b>{mcaName}:</b> {value} (index {index})</li>"""
        return index, value, text


class FlintImage(ImageData, _FlintItemMixIn):
    def __init__(self):
        ImageData.__init__(self)
        _FlintItemMixIn.__init__(self)

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        y, x = index
        image = self.getData(copy=False)
        value = image[index]

        plotItem = self.customItem()
        if plotItem is not None:
            assert plotItem.imageChannel() is not None
            imageName = plotItem.imageChannel().displayName(scan)
        else:
            imageName = "Image"

        data = self.getData(copy=False)
        char = self._getColoredChar(value, data, flintModel)

        xName = "Col/X"
        yName = "Row/Y"

        text = f"""
        <li style="white-space:pre">{char} <b>Value:</b> {value}</li>
        <li style="white-space:pre">     <b>{xName}:</b> {x}</li>
        <li style="white-space:pre">     <b>{yName}:</b> {y}</li>
        """
        return x + 0.5, y + 0.5, text


class TooltipItemManager:

    UL = """<ul style="margin-top: 0px; margin-bottom: 0px; margin-left: 0px; margin-right: 0px; -qt-list-indent: 0">"""

    def __init__(self, parent: qt.QWidget, plot: FlintPlot):
        self.__parent = parent

        self.__toolTipMarker = Marker()
        self.__toolTipMarker.setName("marker-tooltip")
        self.__toolTipMarker.setColor("pink")
        self.__toolTipMarker.setSymbol("+")
        self.__toolTipMarker.setSymbolSize(8)
        self.__toolTipMarker.setVisible(False)
        self.__filterClass = None

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

    def __normalizePickingIndices(self, item, indices: List[int]):
        if isinstance(item, ImageData):
            # Image is a special case cause the index is a tuple of vector y,x
            for i in range(len(indices[0])):
                yield indices[0][i], indices[1][i]
        elif isinstance(item, Histogram):
            # Picking with silx 0.12 and histogram is not consistent with other items
            indices = [i for i in indices if i % 2 == 0]
            if len(indices) == 0:
                return None, None, None
            # Drop other picked indexes + patch silx 0.12
            index = indices[-1] // 2
            yield index
        elif isinstance(item, Curve):
            # Curve picking is picking the segments
            # But we care about points
            xx = item.getXData(copy=False)
            yy = item.getYData(copy=False)
            axis = item.getYAxis()
            mouse = self.__mouse

            # Test both start and stop of the segment
            ii = set([])
            for index in indices:
                ii.add(index)
                ii.add(index + 1)
            ii.discard(len(yy))

            indexes = sorted(ii)
            for index in indexes:
                x = xx[index]
                y = yy[index]
                pos = self.__plot.dataToPixel(x, y, axis=axis)
                if pos is None:
                    continue
                dist = abs(pos[0] - mouse[0]) + abs(pos[1] - mouse[1])
                if dist < 3:
                    yield index
        elif isinstance(item, Scatter):
            for index in indices:
                yield index
        else:
            assert False

    def __picking(self, x, y):
        # FIXME: Hack to avoid to pass it by argument, could be done in better way
        self.__mouse = x, y

        if x is not None:
            if self.__filterClass is not None:
                condition = lambda item: isinstance(item, self.__filterClass)
            else:
                condition = None
            results = [r for r in self.__plot.pickItems(x, y, condition)]
        else:
            results = []
        for result in results:
            item = result.getItem()
            indices = result.getIndices(copy=False)
            for index in self.__normalizePickingIndices(item, indices):
                yield item, index

    def __updateTooltip(self, x, y):
        results = self.__picking(x, y)

        textResult = []
        flintModel = self.__parent.flintModel()
        scan = self.__parent.scan()

        if self.__plot.getGraphCursor() is not None and x is not None:
            plotModel = self.__parent.plotModel()
            text = self.getCrossairTooltip(plotModel, flintModel, scan, x, y)
            textResult.append(text)

        x, y, axis = None, None, None
        for result in results:
            item, index = result
            if isinstance(item, _FlintItemMixIn):
                x, y, text = item.getFlintTooltip(index, flintModel, scan)
                textResult.append(text)
            else:
                continue

            if isinstance(item, (Curve, Histogram)):
                axis = item.getYAxis()
            else:
                axis = "left"

        if textResult != []:
            text = f"<html>{self.UL}" + "".join(textResult) + "</ul></html>"
            self.__updateToolTipMarker(x, y, axis)
            cursorPos = qt.QCursor.pos() + qt.QPoint(10, 10)
            qt.QToolTip.showText(cursorPos, text, self.__plot)
        else:
            self.__updateToolTipMarker(None, None, None)
            qt.QToolTip.hideText()

    def __isY2AxisDisplayed(self):
        for item in self.__plot.getItems():
            if isinstance(item, BoundingRect):
                continue
            if isinstance(item, YAxisMixIn):
                if not item.isVisible():
                    continue
                if item.getYAxis() == "right":
                    return True
        return False

    def getCrossairTooltip(self, plotModel, flintModel, scan, px, py):
        # Get a visible item
        selectedItem = None
        for item in plotModel.items():
            if item.isVisible():
                selectedItem = item
                break

        x, y = self.__plot.pixelToData(px, py)

        y2Name = None
        if isinstance(plotModel, plot_item_model.CurvePlot):
            xName = None
            if isinstance(selectedItem, plot_item_model.CurveItem):
                xChannel = selectedItem.xChannel()
                if xChannel is not None:
                    xName = xChannel.displayName(scan)
            if xName is None:
                xName = "X"
            yName = "Y1"
            if self.__isY2AxisDisplayed():
                _, y2 = self.__plot.pixelToData(px, py, "right")
                y2Name = "Y2"
        elif isinstance(plotModel, plot_item_model.ScatterPlot):
            xName = None
            yName = None
            if isinstance(selectedItem, plot_item_model.CurveItem):
                xChannel = selectedItem.xChannel()
                if xChannel is not None:
                    xName = xChannel.displayName(scan)
            if xName is None:
                xName = "X"
            if isinstance(selectedItem, plot_item_model.ScatterItem):
                yChannel = selectedItem.xChannel()
                if yChannel is not None:
                    yName = yChannel.displayName(scan)
            if yName is None:
                yName = "Y"
        elif isinstance(plotModel, plot_item_model.McaPlot):
            x, y = int(x), int(y)
            xName = "Channel ID"
            yName = "Count"
        elif isinstance(plotModel, plot_item_model.ImagePlot):
            # Round to the pixel
            x, y = int(x), int(y)
            xName = "Col/X"
            yName = "Row/Y"
        else:
            xName = "x"
            yName = "y"

        char = "✛"

        text = f"""
        <li style="white-space:pre">{char} <b>Crossair</b></li>
        <li style="white-space:pre">     <b>{xName}:</b> {x}</li>
        <li style="white-space:pre">     <b>{yName}:</b> {y}</li>
        """
        if y2Name is not None:
            text += f"""
        <li style="white-space:pre">     <b>{y2Name}:</b> {y2}</li>
        """
        return text

    def __updateToolTipMarker(self, x, y, axis):
        if x is None:
            self.__toolTipMarker.setVisible(False)
        else:
            self.__toolTipMarker.setVisible(True)
            self.__toolTipMarker.setPosition(x, y)
            self.__toolTipMarker.setYAxis(axis)


class RefreshManager(qt.QObject):
    """Helper to compute a frame rate"""

    def __init__(self, parent: qt.QWidget):
        super(RefreshManager, self).__init__(parent=parent)
        self.__parent = parent
        self.__lastValues: List[float] = []
        self.__lastUpdate: Optional[float] = None
        self.__aggregator: signalutils.EventAggregator = None

        self.__updater = qt.QTimer(self)
        self.__updater.timeout.connect(self.__update)
        self.__updater.start(500)
        self.__scanProcessing = False

    def scanStarted(self):
        self.__scanProcessing = True
        self.reset()

    def scanFinished(self):
        self.__scanProcessing = False

    def __update(self):
        if self.__aggregator.empty():
            return
        _logger.debug("Update widget")
        if self.__scanProcessing:
            self.update()
        self.__aggregator.flush()

    def setAggregator(self, aggregator):
        self.__aggregator = aggregator

    def __aboutToShowRefreshMode(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        currentRate = self.__currentRefreshMode()

        menu.addSection("Refresh rate")
        rates = [1000, 500, 200, 100]
        for rate in rates:
            action = qt.QAction(menu)
            action.setCheckable(True)
            action.setChecked(currentRate == rate)
            action.setText(f"{rate} ms")
            action.setToolTip(f"Set the refresh rate to {rate} ms")
            action.triggered.connect(functools.partial(self.__setRefreshRate, rate))
            menu.addAction(action)

        action = qt.QAction(menu)
        action.setCheckable(True)
        action.setChecked(currentRate is None)
        action.setText(f"As fast as possible")
        action.setToolTip(f"The plot is updated when a new data is received")
        action.triggered.connect(functools.partial(self.__setRefreshRate, None))
        menu.addAction(action)

        menu.addSection("Mesured rate")
        periode = self.periode()
        if periode is not None:
            periode = round(periode * 1000)
            action = qt.QAction(menu)
            action.setEnabled(False)
            action.setText(f"{periode} ms")
            action.setToolTip(f"Last mesured rate when scan was precessing")
            menu.addAction(action)

    def createRefreshAction(self, parent: qt.QWidget):
        toolButton = qt.QToolButton(parent)
        toolButton.setText("Max refresh mode")
        menu = qt.QMenu(toolButton)
        menu.aboutToShow.connect(self.__aboutToShowRefreshMode)
        toolButton.setMenu(menu)
        toolButton.setToolTip("Custom and check refresh mode applied")
        icon = icons.getQIcon("flint:icons/refresh")
        toolButton.setIcon(icon)
        toolButton.setPopupMode(qt.QToolButton.InstantPopup)
        action = qt.QWidgetAction(parent)
        action.setDefaultWidget(toolButton)
        return action

    def update(self):
        now = time.time()
        if self.__lastUpdate is not None:
            periode = now - self.__lastUpdate
            self.__lastValues.append(periode)
            self.__lastValues = self.__lastValues[-5:]
        else:
            # Clean up the load values
            self.__lastValues = []

        self.__lastUpdate = now

    def reset(self):
        self.__lastUpdate = None

    def frameRate(self):
        if self.__lastValues == []:
            return None
        return 1 / self.periode()

    def periode(self):
        if self.__lastValues == []:
            return None
        return sum(self.__lastValues) / len(self.__lastValues)

    def __currentRefreshMode(self):
        if self.__updater.isActive():
            return self.__updater.interval()
        else:
            return None

    def __setRefreshRate(self, rate):
        if rate is None:
            if self.__updater.isActive():
                self.__updater.stop()
                self.__aggregator.eventAdded.connect(
                    self.__update, qt.Qt.QueuedConnection
                )
        else:
            if self.__updater.isActive():
                self.__updater.setInterval(rate)
            else:
                self.__updater.start(rate)
                self.__aggregator.eventAdded.disconnect(self.__update)


class ViewManager(qt.QObject):

    sigZoomMode = qt.Signal(bool)

    def __init__(self, plot):
        super(ViewManager, self).__init__(parent=plot)
        self.__plot = plot
        self.__plot.sigViewChanged.connect(self.__viewChanged)
        self.__inUserView: bool = False

    def __setUserViewMode(self, userMode):
        if self.__inUserView == userMode:
            return
        self.__inUserView = userMode
        self.sigZoomMode.emit(userMode)

    def __viewChanged(self, event):
        if event.userInteraction:
            self.__setUserViewMode(True)

    def scanStarted(self):
        self.__setUserViewMode(False)

    def resetZoom(self):
        self.__plot.resetZoom()
        self.__setUserViewMode(False)

    def plotUpdated(self):
        if not self.__inUserView:
            self.__plot.resetZoom()

    def plotCleared(self):
        self.__plot.resetZoom()
        self.__setUserViewMode(False)

    def createResetZoomAction(self, parent: qt.QWidget) -> qt.QAction:
        resetZoom = qt.QAction(parent)
        resetZoom.triggered.connect(self.resetZoom)
        resetZoom.setText("Reset zoom")
        resetZoom.setToolTip("Back to the auto-zoom")
        resetZoom.setIcon(icons.getQIcon("flint:icons/zoom-auto"))
        resetZoom.setEnabled(self.__inUserView)

        def updateResetZoomAction(isUserMode):
            resetZoom.setEnabled(isUserMode)

        self.sigZoomMode.connect(updateResetZoomAction)

        return resetZoom
