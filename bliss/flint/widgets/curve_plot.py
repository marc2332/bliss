# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import Tuple
from typing import Union
from typing import Dict
from typing import List

import numpy
import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.items.shape import BoundingRect
from silx.gui.plot.items import Curve
from silx.gui.plot.items import axis as axis_mdl

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget
from bliss.flint.widgets.plot_helper import FlintPlot
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from bliss.flint.utils import signalutils
from bliss.flint.widgets import plot_helper


_logger = logging.getLogger(__name__)


class CurvePlotWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)

    def __init__(self, parent=None):
        super(CurvePlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[
            plot_model.Item, Dict[scan_model.Scan, List[Tuple[str, str]]]
        ] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = FlintPlot(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2, symbol=".")
        self.__plot.setDataMargins(0.1, 0.1, 0.1, 0.1)
        self.setWidget(self.__plot)
        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)
        self.__view = plot_helper.ViewManager(self.__plot)

        self.__aggregator = signalutils.EventAggregator(self)
        self.__refreshManager = plot_helper.RefreshManager(self)
        self.__refreshManager.setAggregator(self.__aggregator)

        toolBar = self.__createToolBar()
        self.__plot.addToolBar(toolBar)

        self.__tooltipManager = plot_helper.TooltipItemManager(self, self.__plot)
        self.__tooltipManager.setFilter(plot_helper.FlintCurve)

        self.__syncAxisTitle = signalutils.InvalidatableSignal(self)
        self.__syncAxisTitle.triggered.connect(self.__updateAxesLabel)
        self.__syncAxisItems = signalutils.InvalidatableSignal(self)
        self.__syncAxisItems.triggered.connect(self.__updateAxesItems)

        self.__bounding = BoundingRect()
        self.__bounding._setLegend("bound")

        self.__permanentItems = [self.__bounding, self.__tooltipManager.marker()]

        for o in self.__permanentItems:
            self.__plot._add(o)

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
        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)
        toolBar.addAction(control.GridAction(self.__plot, "major", self))
        toolBar.addSeparator()

        # Tools

        action = self.__plot.getCurvesRoiDockWidget().toggleViewAction()
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

        toolBar.addSeparator()

        # Export

        # FIXME implement that
        action = qt.QAction(self)
        action.setText("Export to logbook")
        action.setToolTip("Export this plot to the logbook (not yet implemented)")
        icon = icons.getQIcon("flint:icons/export-logbook")
        action.setIcon(icon)
        action.setEnabled(False)
        toolBar.addAction(action)
        toolBar.addAction(plot_helper.ExportOthers(self.__plot, self))

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
        return propertyWidget

    def flintModel(self) -> Optional[flint_model.FlintState]:
        return self.__flintModel

    def setFlintModel(self, flintModel: Optional[flint_model.FlintState]):
        self.__flintModel = flintModel

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
        scan = self.__scan
        if scan is None:
            return
        plotModel = self.__plotModel
        if plotModel is None:
            return
        for item in plotModel.items():
            # FIXME: Use a better abstract concept for that
            if isinstance(item, plot_item_model.MotorPositionMarker):
                self.__updatePlotItem(item, scan)

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
            self.__plot._add(o)

    def __scanStarted(self):
        self.__updateTitle(self.__scan)

    def __updateTitle(self, scan: scan_model.Scan):
        title = scan_info_helper.get_full_title(scan)
        self.__plot.setGraphTitle(title)

    def __scanFinished(self):
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

    def __redrawCurrentScan(self):
        currentScan = self.__scan
        if currentScan is None:
            return
        self.__redrawScan(currentScan)

    def __redrawAllScans(self):
        plot = self.__plot
        plot.clear()
        if self.__plotModel is None:
            for o in self.__permanentItems:
                self.__plot._add(o)
            return

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
            self.__plot._add(o)

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

        self.__cleanScan(scan)
        plotModel = self.__plotModel
        if plotModel is None:
            return

        for item in plotModel.items():
            self.__updatePlotItem(item, scan)

    def __updateItem(self, item: plot_model.Item):
        if self.__plotModel is None:
            return

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

    def __updatePlotItem(self, item: plot_model.Item, scan: scan_model.Scan):
        if not item.isValid():
            return
        if isinstance(item, plot_item_model.ScanItem):
            return

        plot = self.__plot
        plotItems: List[Tuple[str, str]] = []

        updateZoomNow = not self.__plotModel.isInTransaction()

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
            curveItem._setLegend(legend)
            curveItem.setLineStyle(style.lineStyle)
            curveItem.setColor(style.lineColor)
            curveItem.setSymbol("")
            curveItem.setYAxis(item.yAxis())
            plot._add(curveItem)
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
                    curveItem._setLegend(legend)
                    curveItem._setSelectable(False)
                    curveItem.setLineStyle(style.lineStyle)
                    curveItem.setColor(style.lineColor)
                    curveItem.setSymbol("")
                    curveItem.setYAxis(item.yAxis())
                    plot._add(curveItem)
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
                    curveItem._setLegend(legend)
                    curveItem._setSelectable(False)
                    curveItem.setLineStyle(style.lineStyle)
                    curveItem.setColor(style.lineColor)
                    curveItem.setSymbol("")
                    curveItem.setYAxis(item.yAxis())
                    plot._add(curveItem)
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

        elif isinstance(item, plot_item_model.MotorPositionMarker):
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
        self.__updatePlotZoom(updateZoomNow)

    def __updatePlotZoom(self, updateZoomNow):
        if updateZoomNow:
            self.__view.plotUpdated()
        else:
            self.__plotWasUpdated = True
