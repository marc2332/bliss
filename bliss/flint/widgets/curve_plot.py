# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Tuple
from typing import Union
from typing import Dict
from typing import List

import numpy

from silx.gui import qt
from silx.gui.plot import PlotWidget
import silx._version

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model


class CurvePlotWidget(qt.QDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)

    def __init__(self, parent=None):
        super(CurvePlotWidget, self).__init__(parent=parent)
        self.__scan: Union[None, scan_model.Scan] = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[
            plot_model.Item, Dict[scan_model.Scan, List[Tuple[str, str]]]
        ] = {}

        self.__plot = PlotWidget(parent=self, backend="mpl")
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setDataMargins(0.1, 0.1, 0.1, 0.1)
        self.setWidget(self.__plot)
        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)

    def eventFilter(self, widget, event):
        if widget is not self.__plot and widget is not self.__plot.getWidgetHandle():
            return
        if event.type() == qt.QEvent.MouseButtonPress:
            self.widgetActivated.emit(self)
        return widget.eventFilter(widget, event)

    def focusInEvent(self, event):
        self.widgetActivated.emit(self)
        super(CurvePlotWidget, self).focusInEvent(event)

    def createPropertyWidget(self, parent: qt.QWidget):
        from . import curve_plot_property

        propertyWidget = curve_plot_property.CurvePlotPropertyWidget(parent)
        propertyWidget.setFocusWidget(self)
        propertyWidget.setFlintModel(self.__flintModel)
        return propertyWidget

    def setFlintModel(self, flintModel: Union[flint_model.FlintState, None]):
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
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.connect(self.__structureChanged)
            self.__plotModel.itemValueChanged.connect(self.__itemValueChanged)
        self.plotModelUpdated.emit(plotModel)
        self.__redrawAllScans()

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAllScans()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        if eventType == plot_model.ChangeEventType.VISIBILITY:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.YAXIS:
            self.__updateItem(item)

    def __currentScanChanged(
        self, previousScan: scan_model.Scan, newScan: scan_model.Scan
    ):
        self.__setScan(newScan)

    def __setScan(self, scan: scan_model.Scan = None):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated.disconnect(self.__scanDataUpdated)
            self.__scan.scanStarted.disconnect(self.__scanStarted)
            self.__scan.scanFinished.disconnect(self.__scanFinished)
            self.__cleanScanIfNeeded(self.__scan)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated.connect(self.__scanDataUpdated)
            self.__scan.scanStarted.connect(self.__scanStarted)
            self.__scan.scanFinished.connect(self.__scanFinished)
            self.__redrawScan(self.__scan)

    def __cleanScanIfNeeded(self, scan):
        plotModel = self.__plotModel
        if plotModel is None:
            self.__cleanScan(scan)
            return
        for item in plotModel.items():
            if isinstance(item, plot_curve_model.ScanItem):
                if item.scan() is scan:
                    return
        self.__cleanScan(scan)

    def __clear(self):
        self.__items = {}
        self.__plot.clear()

    def __scanStarted(self):
        print("Scan started...")

    def __scanFinished(self):
        print("Scan finished...")

    def __scanDataUpdated(self):
        self.__redrawCurrentScan()

    def __redrawCurrentScan(self):
        currentScan = self.__scan
        if currentScan is None:
            return
        self.__redrawScan(currentScan)

    def __redrawAllScans(self):
        plot = self.__plot
        plot.clear()
        if self.__plotModel is None:
            return

        scanItems = []
        plotModel = self.__plotModel
        for item in plotModel.items():
            if isinstance(item, plot_curve_model.ScanItem):
                scanItems.append(item)

        if len(scanItems) > 0:
            for scan in scanItems:
                self.__redrawScan(scan.scan())
        else:
            currentScan = self.__scan
            if currentScan is None:
                return
            self.__redrawScan(currentScan)

    def __cleanScan(self, scan: scan_model.Scan):
        items = self.__items.pop(scan, {})
        for _item, itemKeys in items.items():
            for key in itemKeys:
                self.__plot.remove(*key)
        self.__plot.resetZoom()

    def __cleanScanItem(self, item: plot_model.Item, scan: scan_model.Scan):
        itemKeys = self.__items.get(scan, {}).pop(item, [])
        for key in itemKeys:
            self.__plot.remove(*key)
        self.__plot.resetZoom()

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
            if isinstance(scanItem, plot_curve_model.ScanItem):
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
        if isinstance(item, plot_curve_model.ScanItem):
            return

        plot = self.__plot
        plotItems: List[Tuple[str, str]] = []

        if not item.isVisible():
            self.__cleanScanItem(item, scan)
            return

        if isinstance(item, plot_curve_model.CurveMixIn):
            if isinstance(item, plot_curve_model.CurveItem):
                x = item.xChannel()
                y = item.yChannel()
                # FIXME: remove legend, use item mapping
                legend = y.name() + "/" + x.name() + "/" + str(scan)
            else:
                legend = str(item) + "/" + str(scan)
            xx = item.xArray(scan)
            yy = item.yArray(scan)
            if xx is None or yy is None:
                # FIXME: the item legend have to be removed
                return

            style = item.getStyle(scan)
            key = plot.addCurve(
                x=xx,
                y=yy,
                legend=legend,
                linestyle=style.lineStyle,
                color=style.lineColor,
                yaxis=item.yAxis(),
            )
            plotItems.append((key, "curve"))

        elif isinstance(item, plot_curve_model.CurveStatisticMixIn):
            if isinstance(item, plot_curve_model.MaxCurveItem):
                legend = str(item) + "/" + str(scan)
                result = item.reachResult(scan)
                if item.isResultValid(result):
                    style = item.getStyle(scan)
                    height = result.max_location_y - result.min_y_value
                    xx = numpy.array([result.max_location_x, result.max_location_x])
                    text_location_y = result.max_location_y + height * 0.1
                    yy = numpy.array([result.max_location_y, text_location_y])
                    key = plot.addCurve(
                        x=xx,
                        y=yy,
                        legend=legend,
                        linestyle=style.lineStyle,
                        color=style.lineColor,
                        yaxis=item.yAxis(),
                    )
                    plotItems.append((key, "curve"))
                    if silx._version.version_info >= (0, 12):
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
                    else:
                        # FIXME: Remove me for the silx release 0.12
                        key = plot.addMarker(
                            legend=legend + "_text",
                            x=result.max_location_x,
                            y=text_location_y,
                            symbol=",",
                            text="max",
                            color=style.lineColor,
                        )
                        plotItems.append((key, "marker"))
                        key = plot.addMarker(
                            legend=legend + "_pos",
                            x=result.max_location_x,
                            y=result.max_location_y,
                            symbol="x",
                            text="",
                            color=style.lineColor,
                        )
                        plotItems.append((key, "marker"))
                else:
                    try:
                        # FIXME: Not only for curves, but also for markers...
                        plot.removeCurve(legend=legend)
                    except:
                        pass

        if scan not in self.__items:
            self.__items[scan] = {}
        self.__items[scan][item] = plotItems
