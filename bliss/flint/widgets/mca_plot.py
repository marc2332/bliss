# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import Tuple
from typing import Dict
from typing import List

import numpy

from silx.gui import qt
from silx.gui.plot import Plot1D

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model


class McaPlotWidget(qt.QDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)

    def __init__(self, parent=None):
        super(McaPlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[Tuple[str, str]]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = Plot1D(parent=self, backend="mpl")
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
        super(McaPlotWidget, self).focusInEvent(event)

    def createPropertyWidget(self, parent: qt.QWidget):
        from . import mca_plot_property

        propertyWidget = mca_plot_property.McaPlotPropertyWidget(parent)
        propertyWidget.setFocusWidget(self)
        propertyWidget.setFlintModel(self.__flintModel)
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

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAll()

    def __transactionFinished(self):
        if self.__plotWasUpdated:
            self.__plotWasUpdated = False
            self.__plot.resetZoom()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        if eventType == plot_model.ChangeEventType.VISIBILITY:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.MCA_CHANNEL:
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
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated.connect(self.__scanDataUpdated)
            self.__scan.scanStarted.connect(self.__scanStarted)
            self.__scan.scanFinished.connect(self.__scanFinished)
        self.__redrawAll()

    def __clear(self):
        self.__items = {}
        self.__plot.clear()

    def __scanStarted(self):
        pass

    def __scanFinished(self):
        pass

    def __scanDataUpdated(self):
        self.__redrawAll()

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
        if not isinstance(item, plot_item_model.McaItem):
            return

        plot = self.__plot
        plotItems: List[Tuple[str, str]] = []

        resetZoom = not self.__plotModel.isInTransaction()

        if not item.isVisible():
            self.__cleanItem(item)
            return

        yChannel = item.mcaChannel()
        if yChannel is None:
            self.__cleanItem(item)
            return
        yy = yChannel.array(self.__scan)
        if yy is None:
            self.__cleanItem(item)
            return
        edges = numpy.arange(len(yy) + 1) - 0.5

        legend = yChannel.name()
        style = item.getStyle(self.__scan)

        key = plot.addHistogram(
            edges=edges,
            histogram=yy,
            legend=legend,
            color=style.lineColor,
            resetzoom=False,
        )
        plotItems.append((key, "histogram"))

        self.__items[item] = plotItems
        if resetZoom:
            self.__plot.resetZoom()
        else:
            self.__plotWasUpdated = True
