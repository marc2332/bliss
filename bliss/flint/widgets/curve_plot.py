# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import Tuple
from typing import Dict
from typing import List
from typing import Sequence

import numpy
import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui import utils as qtutils
from silx.gui.plot.items.shape import XAxisExtent
from silx.gui.plot.items import Curve
from silx.gui.plot.items import axis as axis_mdl
from silx.gui.plot.actions import fit

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.widgets.plot_helper import FlintPlot
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from bliss.flint.utils import signalutils
from bliss.flint.widgets import plot_helper
from bliss.flint.widgets.utils import export_action

from bliss.scanning import scan_math

_logger = logging.getLogger(__name__)


class SpecMode(qt.QObject):

    stateChanged = qt.Signal(bool)
    """Emitted when the enability changed"""

    def __init__(self, parent: qt.QObject = None):
        super(SpecMode, self).__init__(parent=parent)
        self.__enabled = False

    def isEnabled(self) -> bool:
        return self.__enabled

    def setEnabled(self, enabled: bool):
        if self.__enabled == enabled:
            return
        self.__enabled = enabled
        self.stateChanged.emit(enabled)

    def createAction(self):
        action = qt.QAction(self)
        action.setText("Spec statistics")
        action.setToolTip("Enable/disable Spec statistics for boomers")
        action.setCheckable(True)
        icon = icons.getQIcon("flint:icons/spec")
        action.setIcon(icon)
        self.stateChanged.connect(action.setChecked)
        action.toggled.connect(self.setEnabled)
        return action

    def __selectedData(self, plot: FlintPlot) -> Tuple[numpy.ndarray, numpy.ndarray]:
        curve = plot.getActiveCurve()
        if curve is None:
            curves = plot.getAllCurves()
            curves = [c for c in curves if isinstance(c, plot_helper.FlintCurve)]
            if len(curves) != 1:
                return None, None
            curve = curves[0]
        x = curve.getXData()
        y = curve.getYData()
        return x, y

    def initPlot(self, plot: FlintPlot):
        if self.__enabled:
            pass

    def __computeState(self, plot: FlintPlot) -> Optional[str]:
        x, y = self.__selectedData(plot)
        if x is None or y is None:
            return None
        # FIXME: It would be good to cache this statistics
        peak = scan_math.peak2(x, y)
        cen = scan_math.cen(x, y)
        com = scan_math.com(x, y)
        return f"Peak: {peak[0]:.3} ({peak[1]:.3})  Cen: {cen[0]:.3} (FWHM: {cen[1]:.3})  COM: {com:.3}"

    def updateTitle(self, plot: FlintPlot, title: str) -> str:
        if not self.__enabled:
            return title
        state = self.__computeState(plot)
        if state is None:
            return title
        return title + "\n" + state


class CurvePlotWidget(plot_helper.PlotWidget):

    plotItemSelected = qt.Signal(object)
    """Emitted when a flint plot item was selected by the plot"""

    def __init__(self, parent=None):
        super(CurvePlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__specMode = SpecMode(self)
        self.__specMode.stateChanged.connect(self.__specModeChanged)

        self.__items: Dict[
            plot_model.Item, Dict[scan_model.Scan, List[Tuple[str, str]]]
        ] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = FlintPlot(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2, symbol=".")
        self.__plot.setDataMargins(0.02, 0.02, 0.1, 0.1)

        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.sigSelectionChanged.connect(self.__selectionChanged)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)
        self.__plot.setBackgroundColor("white")
        self.__view = plot_helper.ViewManager(self.__plot)
        self.__selectedPlotItem = None

        self.__aggregator = signalutils.EventAggregator(self)
        self.__refreshManager = plot_helper.RefreshManager(self)
        self.__refreshManager.setAggregator(self.__aggregator)

        toolBar = self.__createToolBar()

        # Try to improve the look and feel
        # FIXME: THis should be done with stylesheet
        line = qt.QFrame(self)
        line.setFrameShape(qt.QFrame.HLine)
        line.setFrameShadow(qt.QFrame.Sunken)

        frame = qt.QFrame(self)
        frame.setFrameShape(qt.QFrame.StyledPanel)
        frame.setAutoFillBackground(True)
        layout = qt.QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolBar)
        layout.addWidget(line)
        layout.addWidget(self.__plot)
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(frame)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

        self.__tooltipManager = plot_helper.TooltipItemManager(self, self.__plot)
        self.__tooltipManager.setFilter(plot_helper.FlintCurve)

        self.__syncAxisTitle = signalutils.InvalidatableSignal(self)
        self.__syncAxisTitle.triggered.connect(self.__updateAxesLabel)
        self.__syncAxisItems = signalutils.InvalidatableSignal(self)
        self.__syncAxisItems.triggered.connect(self.__updateAxesItems)

        self.__boundingY1 = XAxisExtent()
        self.__boundingY1.setName("bound-y1")
        self.__boundingY1.setVisible(False)
        self.__boundingY2 = XAxisExtent()
        self.__boundingY2.setName("bound-y2")
        self.__boundingY2.setVisible(False)

        self.__permanentItems = [
            self.__boundingY1,
            self.__boundingY2,
            self.__tooltipManager.marker(),
        ]

        for o in self.__permanentItems:
            self.__plot.addItem(o)

    def configuration(self):
        config = super(CurvePlotWidget, self).configuration()
        config.spec_mode = self.__specMode.isEnabled()
        return config

    def setConfiguration(self, config):
        if config.spec_mode:
            self.__specMode.setEnabled(True)
        super(CurvePlotWidget, self).setConfiguration(config)

    def __specModeChanged(self, enabled):
        self.__updateStyle()
        self.__updateTitle(self.__scan)

    def __updateStyle(self):
        isLive = False
        if self.__scan is not None:
            isLive = self.__scan.state() == scan_model.ScanState.PROCESSING

        if self.__specMode.isEnabled():
            if isLive:
                dataColor = "#add8e6"
                bgColor = "#f0e68c"
            else:
                dataColor = "#f0e68c"
                bgColor = "#d3d3d3"
        else:
            dataColor = None
            bgColor = "transparent"
        self.__plot.setDataBackgroundColor(dataColor)
        self.__plot.setBackgroundColor(bgColor)

    def getRefreshManager(self) -> plot_helper.RefreshManager:
        return self.__refreshManager

    def __createToolBar(self):
        toolBar = qt.QToolBar(self)
        toolBar.setMovable(False)

        from silx.gui.plot.actions import mode
        from silx.gui.plot.actions import control

        toolBar.addAction(mode.ZoomModeAction(self.__plot, self))
        toolBar.addAction(mode.PanModeAction(self.__plot, self))

        resetZoom = self.__view.createResetZoomAction(parent=self)
        toolBar.addAction(resetZoom)
        toolBar.addSeparator()

        # Axis
        action = self.__refreshManager.createRefreshAction(self)
        toolBar.addAction(action)
        toolBar.addAction(plot_helper.CustomAxisAction(self.__plot, self, kind="curve"))
        toolBar.addAction(control.GridAction(self.__plot, "major", self))
        toolBar.addSeparator()

        # Tools

        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)
        action = self.__plot.getCurvesRoiDockWidget().toggleViewAction()
        toolBar.addAction(action)

        action = self.__specMode.createAction()
        toolBar.addAction(action)

        # FIXME implement that
        action = qt.QAction(self)
        action.setText("Raw display")
        action.setToolTip(
            "Show a table of the raw data from the displayed scatter (not yet implemented)"
        )
        icon = icons.getQIcon("flint:icons/raw-view")
        action.setIcon(icon)
        action.setEnabled(False)
        toolBar.addAction(action)

        toolBar.addAction(fit.FitAction(self.__plot, self))

        toolBar.addSeparator()

        # Export

        self.logbookAction = export_action.ExportToLogBookAction(self.__plot, self)
        toolBar.addAction(self.logbookAction)
        toolBar.addAction(export_action.ExportOthersAction(self.__plot, self))

        return toolBar

    def _silxPlot(self):
        """Returns the silx plot associated to this view.

        It is provided without any warranty.
        """
        return self.__plot

    def eventFilter(self, widget, event):
        if widget is not self.__plot and widget is not self.__plot.getWidgetHandle():
            return
        if event.type() == qt.QEvent.MouseButtonPress:
            self.widgetActivated.emit(self)
        return widget.eventFilter(widget, event)

    def createPropertyWidget(self, parent: qt.QWidget):
        from . import curve_plot_property

        propertyWidget = curve_plot_property.CurvePlotPropertyWidget(parent)
        propertyWidget.setFlintModel(self.__flintModel)
        propertyWidget.setFocusWidget(self)
        propertyWidget.plotItemSelected.connect(self.__plotItemSelectedFromProperty)
        return propertyWidget

    def __findItemFromPlotItem(self, requestedItem: plot_model.Item):
        """Returns a silx plot item from a flint plot item."""
        if requestedItem is None:
            return None
        for item in self.__plot.getItems():
            if isinstance(item, plot_helper.FlintCurve):
                plotItem = item.customItem()
                if plotItem is requestedItem:
                    return item
        return None

    def selectedPlotItem(self) -> Optional[plot_model.Item]:
        """Returns the current selected plot item, if one"""
        return self.__selectedPlotItem

    def __selectionChanged(self, current, previous):
        """Callback executed when the selection from the plot was changed"""
        if isinstance(current, plot_helper.FlintCurve):
            selected = current.customItem()
        else:
            selected = None
        self.__selectedPlotItem = selected
        self.plotItemSelected.emit(selected)
        if self.__specMode.isEnabled():
            self.__updateTitle(self.__scan)

    def __plotItemSelectedFromProperty(self, selected):
        """Callback executed when the selection from the property view was
        changed"""
        self.selectPlotItem(selected)

    def selectPlotItem(self, selected: plot_model.Item, force=False):
        """Select a flint plot item"""
        if not force:
            if self.__selectedPlotItem is selected:
                return
            if selected is self.selectedPlotItem():
                # Break reentrant signals
                return
        self.__selectedPlotItem = selected
        item = self.__findItemFromPlotItem(selected)
        # FIXME: We should not use the legend
        if item is None:
            legend = None
        else:
            legend = item.getLegend()
        self.__plot.setActiveCurve(legend)

    def flintModel(self) -> Optional[flint_model.FlintState]:
        return self.__flintModel

    def setFlintModel(self, flintModel: Optional[flint_model.FlintState]):
        self.__flintModel = flintModel
        self.logbookAction.setFlintModel(flintModel)

    def setPlotModel(self, plotModel: plot_model.Plot):
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.disconnect(
                self.__aggregator.callbackTo(self.__structureChanged)
            )
            self.__plotModel.itemValueChanged.disconnect(
                self.__aggregator.callbackTo(self.__itemValueChanged)
            )
            self.__plotModel.transactionFinished.disconnect(
                self.__aggregator.callbackTo(self.__transactionFinished)
            )
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.connect(
                self.__aggregator.callbackTo(self.__structureChanged)
            )
            self.__plotModel.itemValueChanged.connect(
                self.__aggregator.callbackTo(self.__itemValueChanged)
            )
            self.__plotModel.transactionFinished.connect(
                self.__aggregator.callbackTo(self.__transactionFinished)
            )
        self.plotModelUpdated.emit(plotModel)
        self.__redrawAllScans()
        self.__syncAxisTitle.trigger()

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAllScans()
        self.__syncAxisTitle.trigger()

    def __transactionFinished(self):
        if self.__plotWasUpdated:
            self.__plotWasUpdated = False
            self.__view.plotUpdated()
        self.__syncAxisTitle.trigger()
        self.__syncAxisItems.trigger()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        inTransaction = self.__plotModel.isInTransaction()
        if eventType == plot_model.ChangeEventType.VISIBILITY:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.YAXIS:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.X_CHANNEL:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
            self.__syncAxisItems.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.Y_CHANNEL:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)

    def __updateAxesLabel(self):
        scan = self.__scan
        plot = self.__plotModel
        xAxis = None
        if plot is None:
            xLabel = ""
            y1Label = ""
            y2Label = ""
        else:
            xLabels = []
            y1Labels = []
            y2Labels = []
            for item in plot.items():
                if not item.isValid():
                    continue
                if not item.isVisible():
                    continue
                if isinstance(item, plot_item_model.CurveItem):
                    xAxis = item.xChannel().channel(scan)
                    xLabels.append(item.xChannel().displayName(scan))
                    if item.yAxis() == "left":
                        y1Labels.append(item.yChannel().displayName(scan))
                    elif item.yAxis() == "right":
                        y2Labels.append(item.yChannel().displayName(scan))
                    else:
                        pass
            xLabel = " + ".join(sorted(set(xLabels)))
            y1Label = " + ".join(sorted(set(y1Labels)))
            y2Label = " + ".join(sorted(set(y2Labels)))
        self.__plot.getXAxis().setLabel(xLabel)
        self.__plot.getYAxis(axis="left").setLabel(y1Label)
        self.__plot.getYAxis(axis="right").setLabel(y2Label)

        if xAxis is not None:
            axis = self.__plot.getXAxis()
            if xAxis.unit() == "s":
                # FIXME: There is no axis for duration
                # then the elapse time will be displayed in 1970, but it is still fine
                axis.setTickMode(axis_mdl.TickMode.TIME_SERIES)
                axis.setTimeZone("UTC")
            else:
                axis.setTickMode(axis_mdl.TickMode.DEFAULT)

    def __updateAxesItems(self):
        """Update items which have relation with the X axis"""
        self.__curveAxesUpdated()
        scan = self.__scan
        if scan is None:
            return
        if self.__specMode.isEnabled():
            self.__updateTitle(scan)
        plotModel = self.__plotModel
        if plotModel is None:
            return
        for item in plotModel.items():
            # FIXME: Use a better abstract concept for that
            if isinstance(item, plot_item_model.AxisPositionMarker):
                self.__updatePlotItem(item, scan)
        self.__view.resetZoom()

    def __reachRangeForYAxis(
        self, plot, scan, yAxis
    ) -> Optional[Tuple[float, float, float]]:
        xAxis = set([])
        for item in plot.items():
            if isinstance(item, plot_item_model.CurveItem):
                if item.yAxis() != yAxis:
                    continue
                xChannel = item.xChannel()
                if xChannel is not None:
                    xAxis.add(xChannel.channel(scan))
        xAxis.discard(None)
        if len(xAxis) == 0:
            return None

        def getRange(axis: Sequence[scan_model.Channel]):
            vv = set([])
            for a in axis:
                metadata = a.metadata()
                if metadata is None:
                    continue
                v = set([metadata.start, metadata.stop, metadata.min, metadata.max])
                vv.update(v)
            vv.discard(None)
            if len(vv) == 0:
                return None, None
            return min(vv), max(vv)

        xRange = getRange(list(xAxis))
        if xRange[0] is None:
            return None
        return xRange[0], xRange[1]

    def __curveAxesUpdated(self):
        scan = self.__scan
        plot = self.__plotModel
        if plot is None or scan is None:
            return

        result = self.__reachRangeForYAxis(plot, scan, "left")
        if result is None:
            self.__boundingY1.setVisible(False)
        else:
            xMin, xMax = result
            self.__boundingY1.setRange(xMin, xMax)
            self.__boundingY1.setVisible(True)

        result = self.__reachRangeForYAxis(plot, scan, "right")
        if result is None:
            self.__boundingY2.setVisible(False)
        else:
            xMin, xMax = result
            self.__boundingY2.setRange(xMin, xMax)
            self.__boundingY2.setVisible(True)

    def scan(self) -> Optional[scan_model.Scan]:
        return self.__scan

    def setScan(self, scan: scan_model.Scan = None):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].disconnect(
                self.__aggregator.callbackTo(self.__scanDataUpdated)
            )
            self.__scan.scanStarted.disconnect(
                self.__aggregator.callbackTo(self.__scanStarted)
            )
            self.__scan.scanFinished.disconnect(
                self.__aggregator.callbackTo(self.__scanFinished)
            )
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].connect(
                self.__aggregator.callbackTo(self.__scanDataUpdated)
            )
            self.__scan.scanStarted.connect(
                self.__aggregator.callbackTo(self.__scanStarted)
            )
            self.__scan.scanFinished.connect(
                self.__aggregator.callbackTo(self.__scanFinished)
            )
            if self.__scan.state() != scan_model.ScanState.INITIALIZED:
                self.__updateTitle(self.__scan)
        self.scanModelUpdated.emit(scan)
        self.__updateTitle(scan)
        self.__redrawAllScans()

    def __cleanScanIfNeeded(self, scan):
        plotModel = self.__plotModel
        if plotModel is None:
            self.__cleanScan(scan)
            return
        for item in plotModel.items():
            if isinstance(item, plot_item_model.ScanItem):
                if item.scan() is scan:
                    return
        self.__cleanScan(scan)

    def __clear(self):
        self.__items = {}
        self.__plot.clear()
        for o in self.__permanentItems:
            self.__plot.addItem(o)

    def __scanStarted(self):
        self.__updateStyle()
        self.__updateTitle(self.__scan)
        self.__curveAxesUpdated()

    def __updateTitle(self, scan: scan_model.Scan):
        if scan is None:
            title = "No scan"
        else:
            title = scan_info_helper.get_full_title(scan)
            title = self.__specMode.updateTitle(self.__plot, title)
        self.__plot.setGraphTitle(title)

    def __scanFinished(self):
        self.__updateStyle()
        self.__refreshManager.scanFinished()

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        scan = self.__scan
        if scan is None:
            return
        plotModel = self.__plotModel
        if plotModel is None:
            return
        for item in plotModel.items():
            if isinstance(item, plot_item_model.CurveItem):
                if item.isValid():
                    xName = item.xChannel().name()
                    yName = item.yChannel().name()
                    if event.isUpdatedChannelName(xName) or event.isUpdatedChannelName(
                        yName
                    ):
                        self.__updatePlotItem(item, scan)
            elif isinstance(item, plot_model.ChildItem):
                if item.isValid():
                    sources = item.inputData()
                    for source in sources:
                        if source is not None:
                            if event.isUpdatedChannelName(source):
                                self.__updatePlotItem(item, scan)
                                break
        if self.__specMode.isEnabled():
            self.__updateTitle(scan)

    def __redrawCurrentScan(self):
        currentScan = self.__scan
        if currentScan is None:
            return
        self.__redrawScan(currentScan)

    def __redrawAllScans(self):
        plot = self.__plot

        with qtutils.blockSignals(self.__plot):
            plot.clear()
            if self.__plotModel is None:
                for o in self.__permanentItems:
                    self.__plot.addItem(o)
                return

        with qtutils.blockSignals(self):
            scanItems = []
            plotModel = self.__plotModel
            for item in plotModel.items():
                if isinstance(item, plot_item_model.ScanItem):
                    scanItems.append(item)

            if len(scanItems) > 0:
                for scan in scanItems:
                    self.__redrawScan(scan.scan())
            else:
                currentScan = self.__scan
                if currentScan is not None:
                    self.__redrawScan(currentScan)

            for o in self.__permanentItems:
                self.__plot.addItem(o)

    def __cleanScan(self, scan: scan_model.Scan):
        items = self.__items.pop(scan, {})
        for _item, itemKeys in items.items():
            for key in itemKeys:
                self.__plot.remove(*key)
        self.__view.plotCleared()

    def __cleanScanItem(self, item: plot_model.Item, scan: scan_model.Scan) -> bool:
        itemKeys = self.__items.get(scan, {}).pop(item, [])
        if len(itemKeys) == 0:
            return False
        for key in itemKeys:
            self.__plot.remove(*key)
        return True

    def __redrawScan(self, scan: scan_model.Scan):
        assert scan is not None

        with qtutils.blockSignals(self.__plot):
            self.__cleanScan(scan)

        with qtutils.blockSignals(self):
            plotModel = self.__plotModel
            if plotModel is None:
                return

            for item in plotModel.items():
                self.__updatePlotItem(item, scan)

    def __updateItem(self, item: plot_model.Item):
        if self.__plotModel is None:
            return

        selectedPlotItem = self.selectedPlotItem()
        if item is selectedPlotItem:
            reselect = item
        else:
            reselect = None

        with qtutils.blockSignals(self):
            scanItems = []
            plotModel = self.__plotModel
            for scanItem in plotModel.items():
                if isinstance(scanItem, plot_item_model.ScanItem):
                    scanItems.append(scanItem)

            if len(scanItems) > 0:
                for scan in scanItems:
                    self.__updatePlotItem(item, scan.scan())
            else:
                currentScan = self.__scan
                if currentScan is None:
                    return
                self.__updatePlotItem(item, currentScan)

            if reselect is not None:
                self.selectPlotItem(reselect)

    def __updatePlotItem(self, item: plot_model.Item, scan: scan_model.Scan):
        if not item.isValid():
            return
        if isinstance(item, plot_item_model.ScanItem):
            return

        plot = self.__plot
        plotItems: List[Tuple[str, str]] = []

        updateZoomNow = not self.__plotModel.isInTransaction()

        with qtutils.blockSignals(self.__plot):
            wasUpdated = self.__cleanScanItem(item, scan)

        if not item.isVisible():
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        if not item.isValidInScan(scan):
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        if isinstance(item, plot_item_model.CurveMixIn):
            if isinstance(item, plot_item_model.CurveItem):
                x = item.xChannel()
                y = item.yChannel()
                # FIXME: remove legend, use item mapping
                legend = x.name() + "/" + y.name() + "/" + str(scan)
            else:
                legend = str(item) + "/" + str(scan)
            xx = item.xArray(scan)
            yy = item.yArray(scan)
            if xx is None or yy is None:
                # FIXME: the item legend have to be removed
                return

            style = item.getStyle(scan)
            curveItem = plot_helper.FlintCurve()
            curveItem.setCustomItem(item)
            curveItem.setData(x=xx, y=yy, copy=False)
            curveItem.setName(legend)
            curveItem.setLineStyle(style.lineStyle)
            curveItem.setColor(style.lineColor)
            curveItem.setSymbol("")
            curveItem.setYAxis(item.yAxis())
            plot.addItem(curveItem)
            plotItems.append((legend, "curve"))

        elif isinstance(item, plot_state_model.CurveStatisticItem):
            if isinstance(item, plot_state_model.MaxCurveItem):
                legend = str(item) + "/" + str(scan)
                result = item.reachResult(scan)
                if item.isResultValid(result):
                    style = item.getStyle(scan)
                    height = result.max_location_y - result.min_y_value
                    xx = numpy.array([result.max_location_x, result.max_location_x])
                    text_location_y = result.max_location_y + height * 0.1
                    yy = numpy.array([result.max_location_y, text_location_y])

                    curveItem = Curve()
                    curveItem.setData(x=xx, y=yy, copy=False)
                    curveItem.setName(legend)
                    curveItem._setSelectable(False)
                    curveItem.setLineStyle(style.lineStyle)
                    curveItem.setColor(style.lineColor)
                    curveItem.setSymbol("")
                    curveItem.setYAxis(item.yAxis())
                    plot.addItem(curveItem)
                    plotItems.append((legend, "curve"))
                    key = plot.addMarker(
                        legend=legend + "_text",
                        x=result.max_location_x,
                        y=text_location_y,
                        symbol=",",
                        text="max",
                        color=style.lineColor,
                        yaxis=item.yAxis(),
                    )
                    plotItems.append((key, "marker"))
                    key = plot.addMarker(
                        legend=legend + "_pos",
                        x=result.max_location_x,
                        y=result.max_location_y,
                        symbol="x",
                        text="",
                        color=style.lineColor,
                        yaxis=item.yAxis(),
                    )
                    plotItems.append((key, "marker"))
            elif isinstance(item, plot_state_model.MinCurveItem):
                legend = str(item) + "/" + str(scan)
                result = item.reachResult(scan)
                if item.isResultValid(result):
                    style = item.getStyle(scan)
                    height = result.max_y_value - result.min_location_y
                    xx = numpy.array([result.min_location_x, result.min_location_x])
                    text_location_y = result.min_location_y - height * 0.1
                    yy = numpy.array([result.min_location_y, text_location_y])

                    curveItem = Curve()
                    curveItem.setData(x=xx, y=yy, copy=False)
                    curveItem.setName(legend)
                    curveItem._setSelectable(False)
                    curveItem.setLineStyle(style.lineStyle)
                    curveItem.setColor(style.lineColor)
                    curveItem.setSymbol("")
                    curveItem.setYAxis(item.yAxis())
                    plot.addItem(curveItem)
                    plotItems.append((legend, "curve"))
                    key = plot.addMarker(
                        legend=legend + "_text",
                        x=result.min_location_x,
                        y=text_location_y,
                        symbol=",",
                        text="min",
                        color=style.lineColor,
                        yaxis=item.yAxis(),
                    )
                    plotItems.append((key, "marker"))
                    key = plot.addMarker(
                        legend=legend + "_pos",
                        x=result.min_location_x,
                        y=result.min_location_y,
                        symbol="x",
                        text="",
                        color=style.lineColor,
                        yaxis=item.yAxis(),
                    )
                    plotItems.append((key, "marker"))

        elif isinstance(item, plot_item_model.AxisPositionMarker):
            if item.isValid():
                model = self.__plotModel
                if model_helper.isChannelUsedAsAxes(
                    model, item.motorChannel().channel(scan)
                ):
                    legend = str(item) + "/" + str(scan)
                    key = plot.addXMarker(
                        legend=legend + "_text",
                        x=item.position(),
                        text=item.text(),
                        color="black",
                    )
                    plotItems.append((key, "marker"))

        if scan not in self.__items:
            self.__items[scan] = {}
        self.__items[scan][item] = plotItems

        if self.selectedPlotItem() is item:
            with qtutils.blockSignals(self.__plot):
                self.selectPlotItem(item, True)

        self.__updatePlotZoom(updateZoomNow)

    def __updatePlotZoom(self, updateZoomNow):
        if updateZoomNow:
            self.__view.plotUpdated()
        else:
            self.__plotWasUpdated = True
