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
import collections

from silx.gui import qt
from silx.gui import colors
from silx.gui.plot import Plot2D

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper


_ItemDescription = collections.namedtuple("_ItemDescription", ("key", "kind", "shape"))


class ImagePlotWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    plotModelUpdated = qt.Signal(object)

    def __init__(self, parent=None):
        super(ImagePlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[_ItemDescription]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = Plot2D(parent=self)
        self.__plot.getIntensityHistogramAction().setVisible(True)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setDataMargins(0.1, 0.1, 0.1, 0.1)
        self.setWidget(self.__plot)
        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)

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
        from . import image_plot_property

        propertyWidget = image_plot_property.ImagePlotPropertyWidget(parent)
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
        elif eventType == plot_model.ChangeEventType.IMAGE_CHANNEL:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.CUSTOM_STYLE:
            self.__updateItem(item)

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

    def __formatItemTitle(self, scan: scan_model.Scan, item=None):
        if item is None:
            return None
        channel = item.imageChannel()
        if channel is None:
            return None

        frameInfo = ""
        displayName = channel.displayName(scan)
        data = channel.data(scan)
        if data is not None:
            if data.frameId() is not None:
                frameInfo = ", frame id: %s" % data.frameId()
        return f"{displayName}{frameInfo}"

    def __updateTitle(self, scan: scan_model.Scan, item=None):
        title = scan_info_helper.get_full_title(scan)
        itemTitle = self.__formatItemTitle(scan, item)
        if itemTitle is not None:
            title = f"{title}\n{itemTitle}"
        self.__plot.setGraphTitle(title)

    def __scanFinished(self):
        pass

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        plotModel = self.__plotModel
        if plotModel is None:
            return
        for item in plotModel.items():
            if isinstance(item, plot_item_model.ImageItem):
                channelName = item.imageChannel().name()
                if event.isUpdatedChannelName(channelName):
                    self.__updateItem(item)

    def __cleanAll(self):
        for _item, itemKeys in self.__items.items():
            for description in itemKeys:
                self.__plot.remove(description.key, description.kind)
        self.__plot.resetZoom()

    def __cleanItem(self, item: plot_model.Item):
        itemKeys = self.__items.pop(item, [])
        for description in itemKeys:
            self.__plot.remove(description.key, description.kind)
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
        if not isinstance(item, plot_item_model.ImageItem):
            return

        scan = self.__scan
        plot = self.__plot
        plotItems: List[_ItemDescription] = []

        resetZoom = not self.__plotModel.isInTransaction()

        if not item.isVisible():
            self.__cleanItem(item)
            return

        dataChannel = item.imageChannel()
        if dataChannel is None:
            self.__cleanItem(item)
            return
        image = dataChannel.array(self.__scan)
        if image is None:
            self.__cleanItem(item)
            return

        legend = dataChannel.name()
        style = item.getStyle(self.__scan)
        colormap = model_helper.getColormapFromItem(item, style)

        if style.symbolStyle is style_model.SymbolStyle.NO_SYMBOL:
            key = plot.addImage(
                image, legend=legend, resetzoom=False, colormap=colormap
            )
            plotItems.append(_ItemDescription(key, "image", image.shape))
            self.__updateTitle(scan, item)
        else:
            yy = numpy.atleast_2d(numpy.arange(image.shape[0])).T
            xx = numpy.atleast_2d(numpy.arange(image.shape[1]))
            xx = xx * numpy.atleast_2d(numpy.ones(image.shape[0])).T + 0.5
            yy = yy * numpy.atleast_2d(numpy.ones(image.shape[1])) + 0.5
            image, xx, yy = image.reshape(-1), xx.reshape(-1), yy.reshape(-1)
            key = plot.addScatter(
                x=xx, y=yy, value=image, legend=legend, colormap=colormap
            )
            scatter = plot.getScatter(key)
            symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
            if symbolStyle == " ":
                symbolStyle = "o"
            scatter.setSymbol(symbolStyle)
            scatter.setSymbolSize(style.symbolSize)
            plotItems.append(_ItemDescription(key, "scatter", image.shape))

        self.__updateStoredItems(item, resetZoom, plotItems)

    def __updateStoredItems(
        self, item: plot_model.Item, resetZoom: bool, plotItems: List[_ItemDescription]
    ):
        if len(plotItems) == 0:
            return

        if item in self.__items:
            previous = self.__items[item]
            haveChanged = previous[0].shape != plotItems[0].shape
        else:
            haveChanged = True

        self.__items[item] = plotItems

        if not haveChanged:
            return

        if resetZoom:
            self.__plot.resetZoom()
        else:
            self.__plotWasUpdated = True
