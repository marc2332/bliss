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
from typing import NamedTuple

import logging
import numpy

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.actions import histogram
from silx.gui.plot.items.marker import Marker

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.widgets.plot_helper import FlintPlot
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from bliss.flint.widgets import plot_helper


_logger = logging.getLogger(__name__)


class _ItemDescription(NamedTuple):
    key: str
    kind: str
    shape: numpy.ndarray


class ImagePlotWidget(plot_helper.PlotWidget):
    def __init__(self, parent=None):
        super(ImagePlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[_ItemDescription]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = FlintPlot(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setKeepDataAspectRatio(True)
        self.__plot.setDataMargins(0.05, 0.05, 0.05, 0.05)
        self.__plot.getYAxis().setInverted(True)

        # Try to improve the look and feel
        # FIXME: THis should be done with stylesheet
        frame = qt.QFrame(self)
        frame.setFrameShape(qt.QFrame.StyledPanel)
        layout = qt.QVBoxLayout(frame)
        layout.addWidget(self.__plot)
        layout.setContentsMargins(0, 0, 0, 0)
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(frame)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)
        self.__view = plot_helper.ViewManager(self.__plot)

        self.__aggregator = plot_helper.PlotEventAggregator(self)
        self.__refreshManager = plot_helper.RefreshManager(self)
        self.__refreshManager.setAggregator(self.__aggregator)

        toolBar = self.__createToolBar()
        self.__plot.addToolBar(toolBar)

        self.__tooltipManager = plot_helper.TooltipItemManager(self, self.__plot)
        self.__tooltipManager.setFilter(plot_helper.FlintImage)

        self.__minMarker = Marker()
        self.__minMarker.setSymbol("")
        self.__minMarker.setVisible(False)
        self.__minMarker.setColor("pink")
        self.__minMarker.setZValue(0.1)
        self.__minMarker.setName("min")

        self.__maxMarker = Marker()
        self.__maxMarker.setSymbol("")
        self.__maxMarker.setVisible(False)
        self.__maxMarker.setColor("pink")
        self.__maxMarker.setZValue(0.1)
        self.__maxMarker.setName("max")

        self.__hasPreviousImage: bool = False
        """Remember that there was an image before this scan, to avoid to
        override the title at startup and waiting for the first image"""
        self.__imageReceived = 0
        """Count the received image for this scan to allow to clean up the
        screen in the end if nothing was received"""
        self.__lastSubTitle = None
        """Remembers the last subtitle in case it have to be reuse when
        displaying the data from the previous scan"""

        self.__permanentItems = [
            self.__tooltipManager.marker(),
            self.__minMarker,
            self.__maxMarker,
        ]

        for o in self.__permanentItems:
            self.__plot.addItem(o)

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
        toolBar.addAction(plot_helper.CustomAxisAction(self.__plot, self, kind="image"))
        toolBar.addAction(control.GridAction(self.__plot, "major", self))
        toolBar.addSeparator()

        # Tools
        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)
        action = histogram.PixelIntensitiesHistoAction(self.__plot, self)
        icon = icons.getQIcon("flint:icons/histogram")
        action.setIcon(icon)
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
        toolBar.addAction(plot_helper.CustomImageProfileAction(self.__plot, self))

        action = control.ColorBarAction(self.__plot, self)
        icon = icons.getQIcon("flint:icons/colorbar")
        action.setIcon(icon)
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
        from . import image_plot_property

        propertyWidget = image_plot_property.ImagePlotPropertyWidget(parent)
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
        self.__redrawAll()

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAll()

    def __transactionFinished(self):
        if self.__plotWasUpdated:
            self.__plotWasUpdated = False
            self.__view.plotUpdated()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        if eventType == plot_model.ChangeEventType.VISIBILITY:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.IMAGE_CHANNEL:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.CUSTOM_STYLE:
            self.__updateItem(item)

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
            self.__updatePreviousScanData()
            self.__hasPreviousImage = True
        else:
            self.__hasPreviousImage = False
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

        # Note: No redraw here to avoid blinking of the image
        # The image title is explicitly tagged as "outdated"
        # To avoid mistakes
        self.__redrawAllIfNeeded()

    def __clear(self):
        self.__items = {}
        self.__plot.clear()
        for o in self.__permanentItems:
            self.__plot.addItem(o)

    def __scanStarted(self):
        self.__imageReceived = 0
        self.__refreshManager.scanStarted()
        self.__view.scanStarted()
        if not self.__hasPreviousImage:
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

    def __updatePreviousScanData(self):
        """Set the plot title when the plot have to display at start the data
        from the previous scan"""
        title = "From previous scan"
        subtitle = None
        if self.__lastSubTitle is not None:
            subtitle = self.__lastSubTitle
        if subtitle is not None:
            title = f"{title}\n{subtitle}"
        self.__plot.setGraphTitle(title)

    def __updateTitle(self, scan: scan_model.Scan, item=None):
        title = scan_info_helper.get_full_title(scan)
        subtitle = None
        itemTitle = self.__formatItemTitle(scan, item)
        self.__lastSubTitle = itemTitle
        if itemTitle is not None:
            subtitle = f"{itemTitle}"
        if subtitle is not None:
            title = f"{title}\n{subtitle}"
        self.__plot.setGraphTitle(title)

    def __scanFinished(self):
        self.__refreshManager.scanFinished()
        if self.__imageReceived == 0:
            self.__cleanAll()

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        plotModel = self.__plotModel
        if plotModel is None:
            return
        self.__imageReceived += 1
        for item in plotModel.items():
            if isinstance(item, plot_item_model.ImageItem):
                channelName = item.imageChannel().name()
                if event.isUpdatedChannelName(channelName):
                    self.__updateItem(item)

    def __cleanAll(self):
        for _item, itemKeys in self.__items.items():
            for description in itemKeys:
                self.__plot.remove(description.key, description.kind)
        self.__view.plotCleared()

    def __cleanItem(self, item: plot_model.Item):
        itemKeys = self.__items.pop(item, [])
        if len(itemKeys) == 0:
            return False
        for description in itemKeys:
            self.__plot.remove(description.key, description.kind)
        return True

    def __redrawAllIfNeeded(self):
        plotModel = self.__plotModel
        if plotModel is None:
            self.__cleanAll()
            return

        for item in plotModel.items():
            if not isinstance(item, plot_item_model.ImageItem):
                continue
            if not item.isVisible():
                continue
            data = item.imageChannel().data(self.__scan)
            if data is None:
                continue
            self.__redrawAll()

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

        updateZoomNow = not self.__plotModel.isInTransaction()

        wasUpdated = self.__cleanItem(item)

        if not item.isVisible():
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        if not item.isValidInScan(scan):
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        dataChannel = item.imageChannel()
        if dataChannel is None:
            self.__cleanItem(item)
            return
        image = dataChannel.array(self.__scan)
        if image is None:
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        legend = dataChannel.name()
        style = item.getStyle(self.__scan)
        colormap = model_helper.getColormapFromItem(item, style)

        if style.symbolStyle is style_model.SymbolStyle.NO_SYMBOL:
            imageItem = plot_helper.FlintImage()
            imageItem.setColormap(colormap)
            imageItem.setData(image, copy=False)
            imageItem.setCustomItem(item)
            imageItem.setName(legend)
            self.__plot.addItem(imageItem)

            self.__plot._setActiveItem("image", legend)
            plotItems.append(_ItemDescription(legend, "image", image.shape))
            self.__updateTitle(scan, item)

            bottom, left = 0, 0
            height, width = image.shape[0], image.shape[1]
            self.__minMarker.setPosition(0, 0)
            self.__maxMarker.setText(f"{left}, {bottom}")
            self.__minMarker.setVisible(True)
            self.__maxMarker.setPosition(width, height)
            self.__maxMarker.setText(f"{width}, {height}")
            self.__maxMarker.setVisible(True)
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

        self.__items[item] = plotItems
        self.__updatePlotZoom(updateZoomNow)

    def __updatePlotZoom(self, updateZoomNow):
        if updateZoomNow:
            self.__view.plotUpdated()
        else:
            self.__plotWasUpdated = True
