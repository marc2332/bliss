# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Tuple
from typing import Dict
from typing import List
from typing import Optional

from silx.gui import qt
from silx.gui import colors
from silx.gui.plot import Plot1D

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget
from bliss.flint.helper import scan_info_helper
from bliss.flint.utils import signalutils


class ScatterPlotWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)

    def __init__(self, parent=None):
        super(ScatterPlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[Tuple[str, str]]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = Plot1D(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setDataMargins(0.1, 0.1, 0.1, 0.1)
        self.setWidget(self.__plot)
        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)

        self.__syncAxisTitle = signalutils.InvalidatableSignal(self)
        self.__syncAxisTitle.triggered.connect(self.__updateAxesLabel)

    def eventFilter(self, widget, event):
        if widget is not self.__plot and widget is not self.__plot.getWidgetHandle():
            return
        if event.type() == qt.QEvent.MouseButtonPress:
            self.widgetActivated.emit(self)
        return widget.eventFilter(widget, event)

    def createPropertyWidget(self, parent: qt.QWidget):
        from . import scatter_plot_property

        propertyWidget = scatter_plot_property.ScatterPlotPropertyWidget(parent)
        propertyWidget.setFlintModel(self.__flintModel)
        propertyWidget.setFocusWidget(self)
        return propertyWidget

    def setFlintModel(self, flintModel: Optional[flint_model.FlintState]):
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
            self.__setScan(None)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)
            self.__setScan(self.__flintModel.currentScan())

    def setPlotModel(self, plotModel: plot_model.Plot):
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.disconnect(self.__structureChanged)
            self.__plotModel.itemValueChanged.disconnect(self.__itemValueChanged)
            self.__plotModel.transactionFinished.disconnect(self.__transactionFinished)
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.connect(self.__structureChanged)
            self.__plotModel.itemValueChanged.connect(self.__itemValueChanged)
            self.__plotModel.transactionFinished.connect(self.__transactionFinished)
        self.plotModelUpdated.emit(plotModel)
        self.__redrawAll()
        self.__syncAxisTitle.trigger()

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAll()
        self.__syncAxisTitle.trigger()

    def __transactionFinished(self):
        if self.__plotWasUpdated:
            self.__plotWasUpdated = False
            self.__plot.resetZoom()
        self.__syncAxisTitle.validate()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        inTransaction = self.__plotModel.isInTransaction()
        if eventType == plot_model.ChangeEventType.VISIBILITY:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.CUSTOM_STYLE:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.X_CHANNEL:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.Y_CHANNEL:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.VALUE_CHANNEL:
            self.__updateItem(item)

    def __updateAxesLabel(self):
        scan = self.__scan
        plot = self.__plotModel
        if plot is None:
            xLabel = ""
            yLabel = ""
        else:
            xLabels = []
            yLabels = []
            for item in plot.items():
                if not item.isValid():
                    continue
                if isinstance(item, plot_item_model.ScatterItem):
                    xLabels.append(item.xChannel().displayName(scan))
                    yLabels.append(item.yChannel().displayName(scan))
            xLabel = " + ".join(sorted(set(xLabels)))
            yLabel = " + ".join(sorted(set(yLabels)))
        self.__plot.getXAxis().setLabel(xLabel)
        self.__plot.getYAxis().setLabel(yLabel)

    def __currentScanChanged(
        self, previousScan: scan_model.Scan, newScan: scan_model.Scan
    ):
        self.__setScan(newScan)

    def __setScan(self, scan: scan_model.Scan = None):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].disconnect(self.__scanDataUpdated)
            self.__scan.scanStarted.disconnect(self.__scanStarted)
            self.__scan.scanFinished.disconnect(self.__scanFinished)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].connect(self.__scanDataUpdated)
            self.__scan.scanStarted.connect(self.__scanStarted)
            self.__scan.scanFinished.connect(self.__scanFinished)
            if self.__scan.state() != scan_model.ScanState.INITIALIZED:
                self.__updateTitle(self.__scan)
        self.__redrawAll()

    def __clear(self):
        self.__items = {}
        self.__plot.clear()

    def __scanStarted(self):
        self.__updateTitle(self.__scan)

    def __updateTitle(self, scan: scan_model.Scan):
        title = scan_info_helper.get_full_title(scan)
        self.__plot.setGraphTitle(title)

    def __scanFinished(self):
        pass

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        plotModel = self.__plotModel
        if plotModel is None:
            return
        for item in plotModel.items():
            if not isinstance(item, plot_item_model.ScatterItem):
                continue
            if not item.isValid():
                continue
            # Create an API to return the involved channel names
            xName = item.xChannel().name()
            yName = item.yChannel().name()
            valueName = item.valueChannel().name()
            if (
                event.isUpdatedChannelName(xName)
                or event.isUpdatedChannelName(yName)
                or event.isUpdatedChannelName(valueName)
            ):
                self.__updateItem(item)

    def __cleanAll(self):
        for _item, itemKeys in self.__items.items():
            for key in itemKeys:
                self.__plot.remove(*key)
        self.__plot.resetZoom()

    def __cleanItem(self, item: plot_model.Item):
        itemKeys = self.__items.pop(item, [])
        for key in itemKeys:
            self.__plot.remove(*key)
        self.__plot.resetZoom()

    def __redrawAll(self):
        self.__cleanAll()
        plotModel = self.__plotModel
        if plotModel is None:
            return

        for item in plotModel.items():
            self.__updateItem(item)

    def __updateItem(self, item: plot_model.Item):
        if self.__plotModel is None:
            return
        if self.__scan is None:
            return
        if not item.isValid():
            return
        if not isinstance(item, plot_item_model.ScatterItem):
            return

        scan = self.__scan
        plot = self.__plot
        plotItems: List[Tuple[str, str]] = []

        resetZoom = not self.__plotModel.isInTransaction()

        self.__cleanItem(item)

        if not item.isVisible():
            return

        if not item.isValidInScan(scan):
            return

        valueChannel = item.valueChannel()
        xChannel = item.xChannel()
        yChannel = item.yChannel()
        if valueChannel is None or xChannel is None or yChannel is None:
            return

        value = valueChannel.array(scan)
        xx = xChannel.array(scan)
        yy = yChannel.array(scan)
        if value is None or xx is None or yy is None:
            return

        legend = valueChannel.name()
        style = item.getStyle(scan)
        colormap = colors.Colormap(style.colormapLut)

        if style.fillStyle is not None:
            key = plot.addScatter(
                x=xx, y=yy, value=value, legend=legend + "_solid", colormap=colormap
            )
            scatter = plot.getScatter(key)
            if style.fillStyle == style_model.FillStyle.SCATTER_REGULAR_GRID:
                scatter.setVisualization(scatter.Visualization.REGULAR_GRID)
            elif style.fillStyle == style_model.FillStyle.SCATTER_INTERPOLATION:
                scatter.setVisualization(scatter.Visualization.SOLID)
            else:
                pass
            plotItems.append((key, "scatter"))

        if style.lineStyle == style_model.LineStyle.SCATTER_SEQUENCE:
            key = plot.addCurve(
                x=xx,
                y=yy,
                legend=legend + "_line",
                color=style.lineColor,
                linestyle="-",
            )
            plotItems.append((key, "curve"))

        if style.symbolStyle is not None:
            symbolColormap = colormap if style.symbolColor is None else None
            if symbolColormap:
                key = plot.addScatter(
                    x=xx,
                    y=yy,
                    value=value,
                    legend=legend + "_point",
                    colormap=symbolColormap,
                )
                scatter = plot.getScatter(key)
                scatter.setSymbol(style.symbolStyle)
                scatter.setSymbolSize(style.symbolSize)
                plotItems.append((key, "scatter"))
            else:
                key = plot.addCurve(
                    x=xx,
                    y=yy,
                    legend=legend + "_point",
                    color=style.symbolColor,
                    symbol=style.symbolStyle,
                    linestyle=" ",
                )
                curve = plot.getCurve(key)
                curve.setSymbolSize(style.symbolSize)
                plotItems.append((key, "curve"))

        self.__items[item] = plotItems
        if resetZoom:
            self.__plot.resetZoom()
        else:
            self.__plotWasUpdated = True
