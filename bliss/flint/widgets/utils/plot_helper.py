# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import NamedTuple
from typing import Optional
from typing import List
from typing import Tuple
from typing import Set
from typing import Dict
from typing import Any

import contextlib
import numpy
import logging

from silx.gui import qt
from silx.gui.plot import PlotWindow
from silx.gui.plot.items.scatter import Scatter
from silx.gui.plot.items.curve import Curve
from silx.gui.plot.items.histogram import Histogram
from silx.gui.plot.items.image import ImageData
from silx.gui.plot.items.image import ImageRgba

from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.model import scan_model
from bliss.flint.utils import signalutils
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget

from .refresh_helper import RefreshManager


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


class ScalarEventAggregator(signalutils.EventAggregator):
    def reduce(self, eventStack: List) -> Tuple[List, List]:
        """Override the method to reduce plot refresh by
        removing duplication events.
        """
        result = []
        # Reduce specific channel events
        fullDevices = set()
        fullAggregation = set()
        currentAggregation = set()
        currentScan = None
        currentCallback = None

        def flush():
            nonlocal currentAggregation, currentScan, currentCallback
            if len(currentAggregation) == 0:
                return
            e = scan_model.ScanDataUpdateEvent(
                currentScan, channels=list(currentAggregation)
            )
            result.insert(0, (currentCallback, [e], {}))
            currentAggregation = set()
            currentScan = None
            currentCallback = None

        for event in reversed(eventStack):
            callback, args, kwargs = event
            if len(args) == 0:
                result.insert(0, event)
                continue
            e = args[0]
            if not isinstance(e, scan_model.ScanDataUpdateEvent):
                result.insert(0, event)
                continue

            if kwargs != {}:
                result.insert(0, event)
                continue

            channels = e.selectedChannels()
            device = e.selectedDevice()
            if channels is not None:
                if fullAggregation.issuperset(channels):
                    continue
                if currentCallback is None or currentCallback is callback:
                    currentCallback = callback
                    currentScan = e.scan()
                    fullAggregation.update(channels)
                    currentAggregation.update(channels)
                else:
                    flush()
                    result.insert(0, event)
            elif device is not None:
                if device in fullDevices:
                    continue
                fullDevices.add(device)
                result.insert(0, event)
            else:
                flush()
                result.insert(0, event)
        flush()
        return result, []


class PlotWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)
    """Emitted when the plot model displayed by the plot was changed"""

    scanModelUpdated = qt.Signal(object)
    """Emitted when the scan model displayed by the plot was changed"""

    def configuration(self):
        plot = self._silxPlot()
        config = plot.configuration()

        if hasattr(self, "getRefreshManager"):
            refreshManager: RefreshManager = self.getRefreshManager()
            if refreshManager is not None:
                rate = refreshManager.refreshMode()
                config.refresh_mode = rate

        if hasattr(self, "deviceName"):
            deviceName = self.deviceName()
            config.device_name = deviceName

        return config

    def setConfiguration(self, config):
        plot = self._silxPlot()
        if hasattr(self, "getRefreshManager"):
            refreshManager: RefreshManager = self.getRefreshManager()
            if refreshManager is not None:
                rate = config.refresh_mode
                refreshManager.setRefreshMode(rate)
        if hasattr(self, "deviceName"):
            deviceName = config.device_name
            if deviceName is not None:
                self.setDeviceName(deviceName)
            else:
                # FIXME: backward compatibility with BLISS <= 1.7
                # This is stored in the Redis db and mostly never updated
                # So it is not so easy to remove
                deviceName = self.windowTitle().split(" ", 1)[0]
            self.setDeviceName(deviceName)

        plot.setConfiguration(config)


class PlotConfiguration:
    """Store a plot configuration for serialization"""

    def __init__(self):
        # Mode
        self.interaction_mode: Optional[str] = None
        self.refresh_mode: Optional[int] = None
        # Axis
        self.x_axis_scale: Optional[str] = None
        self.y_axis_scale: Optional[str] = None
        self.y2_axis_scale: Optional[str] = None
        self.y_axis_inverted: bool = False
        self.y2_axis_inverted: bool = False
        self.fixed_aspect_ratio: bool = False
        # View
        self.grid_mode: bool = False
        self.axis_displayed: bool = True
        # Tools
        self.crosshair_enabled: bool = False
        self.colorbar_displayed: bool = False
        self.profile_widget_displayed: bool = False
        self.roi_widget_displayed: bool = False
        self.histogram_widget_displayed: bool = False

        # Widget displaying dedicated detectors (MCAs, images, one dim)
        self.device_name: str = None

        # Curve widget
        self.spec_mode: bool = False

        # Image/scatter widget
        self.colormap: Optional[Dict] = None
        self.profile_state: bytes = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        """Inherit the serialization to make sure the object can grow up in the
        future"""
        state: Dict[str, Any] = {}
        state.update(self.__dict__)
        return state

    def __setstate__(self, state):
        """Inherit the serialization to make sure the object can grow up in the
        future"""
        for k in self.__dict__.keys():
            if k in state:
                v = state.pop(k)
                self.__dict__[k] = v

    def __str__(self):
        return self.__dict__.__str__()


class _MousePressedListener(qt.QObject):
    """
    Dedicated `eventFilter` to dispatch pressevent from the plot handler.
    """

    def __init__(self, parent=None):
        qt.QObject.__init__(self, parent=parent)

    def eventFilter(self, widget, event):
        if event.type() == qt.QEvent.MouseButtonPress:
            parent = self.parent()
            parent.sigMousePressed.emit()
        return widget.eventFilter(widget, event)


class FlintPlot(PlotWindow):
    """Helper to provide few other functionalities on top of silx.

    This should be removed and merged into silx.
    """

    sigViewChanged = qt.Signal(ViewChangedEvent)

    sigMouseMoved = qt.Signal(MouseMovedEvent)

    sigMouseLeft = qt.Signal()

    sigMousePressed = qt.Signal()

    def __init__(self, parent=None, backend=None):
        self._mousePressedListener = None
        super(FlintPlot, self).__init__(parent=parent, backend=backend)
        self.sigPlotSignal.connect(self.__plotEvents)
        self.__userInteraction = False

        toolbars = self.findChildren(qt.QToolBar)
        for tb in toolbars:
            self.removeToolBar(tb)

        self._mousePressedListener = _MousePressedListener(self)

        self._backendUpdated()

    def setBackend(self, backend):
        super(FlintPlot, self).setBackend(backend)
        self._backendUpdated()

    def _backendUpdated(self):
        if hasattr(self, "centralWidget"):
            self.centralWidget().installEventFilter(self)

        if self._mousePressedListener is not None:
            self.installEventFilter(self._mousePressedListener)
            self.getWidgetHandle().installEventFilter(self._mousePressedListener)

    def configuration(self) -> PlotConfiguration:
        """Returns a global configuration of the plot"""
        config = PlotConfiguration()

        mode = self.getInteractiveMode()["mode"]
        if mode not in ("pan", "zoom"):
            mode = None
        config.interaction_mode = mode

        # Axis
        axis = self.getXAxis()
        config.x_axis_scale = axis.getScale()
        axis = self.getYAxis()
        config.y_axis_scale = axis.getScale()
        config.y_axis_inverted = axis.isInverted()
        axis = self.getYAxis("right")
        config.y2_axis_scale = axis.getScale()
        config.y2_axis_inverted = axis.isInverted()
        config.fixed_aspect_ratio = self.isKeepDataAspectRatio()

        # View
        config.grid_mode = self.getGraphGrid()
        config.axis_displayed = self.isAxesDisplayed()

        # Tools
        config.crosshair_enabled = self.getGraphCursor() is not None
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
        with safeApply():
            self.setKeepDataAspectRatio(config.fixed_aspect_ratio)

        # View
        with safeApply():
            self.setGraphGrid(config.grid_mode)
        with safeApply():
            self.setAxesDisplayed(config.axis_displayed)

        # Tools
        if config.crosshair_enabled:
            with safeApply():
                self.setGraphCursor(True)
        if config.colorbar_displayed:
            with safeApply():
                self.getColorBarWidget().setVisible(True)

    def graphCallback(self, ddict=None):
        """
        Override silx function to avoid to call QToolTip.showText when a curve
        is selected.
        """
        # FIXME it would be very good to remove this code and this function
        if ddict is None:
            ddict = {}
        if ddict["event"] in ["legendClicked", "curveClicked"]:
            if ddict["button"] == "left":
                self.setActiveCurve(ddict["label"])
        elif ddict["event"] == "mouseClicked" and ddict["button"] == "left":
            self.setActiveCurve(None)

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


class FlintItemMixIn:
    def __init__(self):
        self.__plotItem = None
        self.__scan = None

    def customItem(self) -> Optional[plot_model.Item]:
        return self.__plotItem

    def setCustomItem(self, item: plot_model.Item):
        self.__plotItem = item

    def setScan(self, scan):
        self.__scan = scan

    def scan(self):
        return self.__scan

    def getFlintTooltip(
        self, index, flintModel, scan: scan_model.Scan
    ) -> Tuple[int, int, str]:
        return None, None, None

    def _getColoredChar(self, value, flintModel):
        colormap = self.getColormap()
        data = numpy.array([float(value)])
        colors = colormap.applyToData(data, reference=self)
        cssColor = f"#{colors[0,0]:02X}{colors[0,1]:02X}{colors[0,2]:02X}"

        if flintModel is not None and flintModel.getDate() == "0214":
            char = "\u2665"
        else:
            char = "■"
        return f"""<font color="{cssColor}">{char}</font>"""

    def _getColoredSymbol(self, flintModel, scan: scan_model.Scan):
        """Returns a colored HTML char according to the expected plot item style
        """
        if scan is None:
            scan = self.__scan
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


class FlintScatter(Scatter, FlintItemMixIn):
    def __init__(self):
        Scatter.__init__(self)
        FlintItemMixIn.__init__(self)
        self.__indexes = None

    def setRealIndexes(self, indexes):
        """Specify a scatter following the axis and values, which hold the real
        index from the real data."""
        self.__indexes = indexes

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        # Drop other picked indexes
        x = self.getXData(copy=False)[index]
        y = self.getYData(copy=False)[index]
        value = self.getValueData(copy=False)[index]
        if self.__indexes is not None:
            index = self.__indexes[index]

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

        char = self._getColoredChar(value, flintModel)

        text = f"""
            <li style="white-space:pre">{char} <b>{vName}:</b> {value} (index {index})</li>
            <li style="white-space:pre">     <b>{yName}:</b> {y}</li>
            <li style="white-space:pre">     <b>{xName}:</b> {x}</li>
        """
        return x, y, text


class FlintCurve(Curve, FlintItemMixIn):
    def __init__(self):
        Curve.__init__(self)
        FlintItemMixIn.__init__(self)

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

        char = self._getColoredSymbol(flintModel, None)

        text = f"""
        <li style="white-space:pre">{char} <b>{yName}:</b> {yValue} (index {index})</li>
        <li style="white-space:pre">     <b>{xName}:</b> {xValue}</li>
        """

        if isinstance(plotItem, plot_state_model.GaussianFitItem):
            result = plotItem.reachResult(scan)
            if result is not None:
                text += f"""
                <li style="white-space:pre">     <b>FWHM:</b> {result.fit.fwhm}</li>
                <li style="white-space:pre">     <b>std dev (σ):</b> {result.fit.std}</li>
                <li style="white-space:pre">     <b>position (μ):</b> {result.fit.pos_x}</li>
                """

        return xValue, yValue, text


class FlintRawMca(Histogram, FlintItemMixIn):
    def __init__(self):
        Histogram.__init__(self)
        FlintItemMixIn.__init__(self)

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


class FlintImage(ImageData, FlintItemMixIn):
    def __init__(self):
        ImageData.__init__(self)
        FlintItemMixIn.__init__(self)

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        y, x = index
        image = self.getData(copy=False)
        value = image[index]
        char = self._getColoredChar(value, flintModel)

        xName = "Col/X"
        yName = "Row/Y"

        text = f"""
        <li style="white-space:pre">{char} <b>Value:</b> {value}</li>
        <li style="white-space:pre">     <b>{xName}:</b> {x}</li>
        <li style="white-space:pre">     <b>{yName}:</b> {y}</li>
        """
        return x + 0.5, y + 0.5, text


class FlintImageRgba(ImageRgba, FlintItemMixIn):
    def __init__(self):
        ImageRgba.__init__(self)
        FlintItemMixIn.__init__(self)

    def getFlintTooltip(self, index, flintModel, scan: scan_model.Scan):
        y, x = index
        image = self.getData(copy=False)
        value = image[index]
        char = self._getColoredChar(value, flintModel)

        xName = "Col/X"
        yName = "Row/Y"

        text = f"""
        <li style="white-space:pre">{char} <b>RGB(A):</b> {value}</li>
        <li style="white-space:pre">     <b>{xName}:</b> {x}</li>
        <li style="white-space:pre">     <b>{yName}:</b> {y}</li>
        """
        return x + 0.5, y + 0.5, text
