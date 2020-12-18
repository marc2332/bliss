# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import Dict
from typing import List
from typing import NamedTuple

import logging
import numpy

from silx.gui import qt
from silx.gui import icons
from silx.gui import colors
from silx.gui.plot.actions import histogram
from silx.gui.plot.items.marker import Marker
from silx.gui.plot.tools.roi import RegionOfInterestManager
from silx.gui.plot.items import roi as silx_rois
from bliss.controllers.lima import roi as lima_rois
from bliss.flint.widgets.utils import rois as flint_rois

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from .utils import plot_helper
from .utils import view_helper
from .utils import refresh_helper
from .utils import tooltip_helper
from .utils import export_action
from .utils import marker_action
from .utils import camera_live_action
from .utils import profile_action
from .utils import plot_action
from .utils import style_action


_logger = logging.getLogger(__name__)


class _ItemDescription(NamedTuple):
    key: str
    kind: str
    shape: numpy.ndarray


class _Title:
    def __init__(self, plot):
        self.__plot = plot

        self.__hasPreviousImage: bool = False
        """Remember that there was an image before this scan, to avoid to
        override the title at startup and waiting for the first image"""
        self.__lastSubTitle = None
        """Remembers the last subtitle in case it have to be reuse when
        displaying the data from the previous scan"""

    def itemUpdated(self, scan, item):
        self.__updateAll(scan, item)

    def scanRemoved(self, scan):
        """Removed scan, just before using another scan"""
        if scan is not None:
            self.__updateTitle("From previous scan")
            self.__hasPreviousImage = True
        else:
            self.__hasPreviousImage = False

    def scanStarted(self, scan):
        if not self.__hasPreviousImage:
            self.__updateAll(scan)

    def scanFinished(self, scan):
        title = scan_info_helper.get_full_title(scan)
        if scan.state() == scan_model.ScanState.FINISHED:
            title += " (finished)"
        self.__updateTitle(title)

    def __formatItemTitle(self, scan: scan_model.Scan, item=None):
        if item is None:
            return None
        channel = item.imageChannel()
        if channel is None:
            return None

        frameInfo = ""
        displayName = channel.displayName(scan)
        shape = ""
        data = channel.data(scan)
        if data is not None:
            array = data.array()
            if array is not None:
                height, width = array.shape[0:2]
                shape = f": {width} × {height}"

            if data.source() == "video":
                op = " ≈ "
            else:
                op = " = "

            if data.frameId() is not None:
                frameInfo = f", id{op}{data.frameId()}"
            if frameInfo != "":
                frameInfo += " "
            frameInfo += f"[{data.source()}]"
        return f"{displayName}{shape}{frameInfo}"

    def __updateTitle(self, title):
        subtitle = None
        if self.__lastSubTitle is not None:
            subtitle = self.__lastSubTitle
        if subtitle is not None:
            title = f"{title}\n{subtitle}"
        self.__plot.setGraphTitle(title)

    def __updateAll(self, scan: scan_model.Scan, item=None):
        title = scan_info_helper.get_full_title(scan)
        subtitle = None
        itemTitle = self.__formatItemTitle(scan, item)
        self.__lastSubTitle = itemTitle
        if itemTitle is not None:
            subtitle = f"{itemTitle}"
        if subtitle is not None:
            title = f"{title}\n{subtitle}"
        self.__plot.setGraphTitle(title)


class ImagePlotWidget(plot_helper.PlotWidget):
    def __init__(self, parent=None):
        super(ImagePlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[_ItemDescription]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = plot_helper.FlintPlot(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setKeepDataAspectRatio(True)
        self.__plot.setDataMargins(0.05, 0.05, 0.05, 0.05)
        self.__plot.getYAxis().setInverted(True)

        self.__roiManager = RegionOfInterestManager(self.__plot)
        self.__profileAction = None

        self.__title = _Title(self.__plot)

        self.__colormap = colors.Colormap("viridis")
        """Each detector have a dedicated widget and a dedicated colormap"""
        self.__colormapInitialized = False

        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)
        self.__view = view_helper.ViewManager(self.__plot)
        self.__view.setResetWhenScanStarts(False)
        self.__view.setResetWhenPlotCleared(False)

        self.__aggregator = plot_helper.PlotEventAggregator(self)
        self.__refreshManager = refresh_helper.RefreshManager(self)
        self.__refreshManager.refreshModeChanged.connect(self.__refreshModeChanged)
        self.__refreshManager.setAggregator(self.__aggregator)

        toolBar = self.__createToolBar()

        # Try to improve the look and feel
        # FIXME: This should be done with stylesheet
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

        self.__tooltipManager = tooltip_helper.TooltipItemManager(self, self.__plot)
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

        self.__imageReceived = 0
        """Count the received image for this scan to allow to clean up the
        screen in the end if nothing was received"""

        self.__plot.addItem(self.__tooltipManager.marker())
        self.__plot.addItem(self.__minMarker)
        self.__plot.addItem(self.__maxMarker)

        self.widgetActivated.connect(self.__activated)

    def __activated(self):
        self.__initColormapWidget()

    def __initColormapWidget(self):
        flintModel = self.flintModel()
        if flintModel is None:
            return
        live = flintModel.liveWindow()
        colormapWidget = live.acquireColormapWidget(self)
        if colormapWidget is not None:
            for item in self.__plot.getItems():
                if isinstance(item, plot_helper.FlintImage):
                    colormapWidget.setItem(item)
                    break
            else:
                colormapWidget.setColormap(self.__colormap)

    def deviceName(self):
        # FIXME: This have to be saved in the configuration
        return self.windowTitle().split(" ")[0]

    def configuration(self):
        config = super(ImagePlotWidget, self).configuration()
        try:
            config.colormap = self.__colormap._toDict()
        except Exception:
            # As it relies on private API, make it safe
            _logger.error("Impossible to save colormap preference", exc_info=True)

        config.profile_state = self.__profileAction.saveState()
        return config

    def setConfiguration(self, config):
        if config.colormap is not None:
            try:
                self.__colormap._setFromDict(config.colormap)
                self.__colormapInitialized = True
            except Exception:
                # As it relies on private API, make it safe
                _logger.error(
                    "Impossible to restore colormap preference", exc_info=True
                )
        if config.profile_state is not None:
            self.__profileAction.restoreState(config.profile_state)

        super(ImagePlotWidget, self).setConfiguration(config)

    def defaultColormap(self):
        return self.__colormap

    def getRefreshManager(self) -> plot_helper.RefreshManager:
        return self.__refreshManager

    def __createToolBar(self):
        toolBar = qt.QToolBar(self)
        toolBar.setMovable(False)

        from silx.gui.plot.actions import mode
        from silx.gui.plot.actions import control
        from silx.gui.widgets.MultiModeAction import MultiModeAction

        modeAction = MultiModeAction(self)
        modeAction.addAction(mode.ZoomModeAction(self.__plot, self))
        modeAction.addAction(mode.PanModeAction(self.__plot, self))
        toolBar.addAction(modeAction)

        resetZoom = self.__view.createResetZoomAction(parent=self)
        toolBar.addAction(resetZoom)
        toolBar.addSeparator()

        # Axis
        action = self.__refreshManager.createRefreshAction(self)
        toolBar.addAction(action)
        toolBar.addAction(plot_action.CustomAxisAction(self.__plot, self, kind="image"))
        toolBar.addSeparator()

        # Item
        action = style_action.FlintSharedColormapAction(self.__plot, self)
        action.setInitColormapWidgetCallback(self.__initColormapWidget)
        toolBar.addAction(action)
        self.__contrastAction = action
        toolBar.addSeparator()

        # Tools
        self.liveAction = camera_live_action.CameraLiveAction(self)
        toolBar.addAction(self.liveAction)
        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)
        action = histogram.PixelIntensitiesHistoAction(self.__plot, self)
        icon = icons.getQIcon("flint:icons/histogram")
        action.setIcon(icon)
        toolBar.addAction(action)

        self.__profileAction = profile_action.ProfileAction(self.__plot, self, "image")
        toolBar.addAction(self.__profileAction)

        action = marker_action.MarkerAction(plot=self.__plot, parent=self, kind="image")
        self.__markerAction = action
        toolBar.addAction(action)

        action = control.ColorBarAction(self.__plot, self)
        icon = icons.getQIcon("flint:icons/colorbar")
        action.setIcon(icon)
        toolBar.addAction(action)
        toolBar.addSeparator()

        # Export

        self.__exportAction = export_action.ExportAction(self.__plot, self)
        toolBar.addAction(self.__exportAction)

        return toolBar

    def logbookAction(self):
        """Expose a logbook action if one"""
        return self.__exportAction.logbookAction()

    def _silxPlot(self):
        """Returns the silx plot associated to this view.

        It is provided without any warranty.
        """
        return self.__plot

    def eventFilter(self, widget, event):
        if widget is self.__plot or widget is self.__plot.getWidgetHandle():
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
        self.__exportAction.setFlintModel(flintModel)
        self.__contrastAction.setFlintModel(flintModel)

        if flintModel is not None:
            if not self.__colormapInitialized:
                style = flintModel.defaultImageStyle()
                self.__colormap.setName(style.colormapLut)

    def setPlotModel(self, plotModel: plot_model.Plot):
        if self.__plotModel is not None:
            self.__plotModel.itemAdded.disconnect(
                self.__aggregator.callbackTo(self.__itemAdded)
            )
            self.__plotModel.itemRemoved.disconnect(
                self.__aggregator.callbackTo(self.__itemRemoved)
            )
            self.__plotModel.structureChanged.disconnect(
                self.__aggregator.callbackTo(self.__structureChanged)
            )
            self.__plotModel.itemValueChanged.disconnect(
                self.__aggregator.callbackTo(self.__itemValueChanged)
            )
            self.__plotModel.transactionFinished.disconnect(
                self.__aggregator.callbackTo(self.__transactionFinished)
            )
        previousPlot = self.__plotModel
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.itemAdded.connect(
                self.__aggregator.callbackTo(self.__itemAdded)
            )
            self.__plotModel.itemRemoved.connect(
                self.__aggregator.callbackTo(self.__itemRemoved)
            )
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
        self.__updatePreferedRefreshRate(
            previousPlot=previousPlot, plot=self.__plotModel
        )
        self.__redrawAll()

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAll()

    def __itemAdded(self, item):
        self.__updatePreferedRefreshRate(newItem=item)

    def __itemRemoved(self, item):
        self.__updatePreferedRefreshRate(previousItem=item)

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
        self.liveAction.setScan(scan)
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
        self.__title.scanRemoved(self.__scan)
        previousScan = self.__scan
        self.__scan = scan
        # As the scan was updated, clear the previous cached events
        self.__aggregator.clear()
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
                self.__title.scanStarted(self.__scan)
        self.scanModelUpdated.emit(scan)

        # Note: No redraw here to avoid blinking of the image
        # The image title is explicitly tagged as "outdated"
        # To avoid mistakes
        self.__updatePreferedRefreshRate(previousScan=previousScan, scan=self.__scan)
        self.__redrawAllIfNeeded()

    def __refreshModeChanged(self):
        self.__updatePreferedRefreshRate()

    def __updatePreferedRefreshRate(
        self,
        previousScan: scan_model.Scan = None,
        scan: scan_model.Scan = None,
        previousPlot: plot_model.Plot = None,
        plot: plot_model.Plot = None,
        previousItem: plot_model.Item = None,
        newItem: plot_model.Item = None,
    ):
        """Propagate prefered refresh rate to the internal scan model.

        This allow the scan manager to optimize image download.

        The function deals with all the cases which can happen. Changes of the
        scan, the plot, or the items. Item visibility could also be taken into
        account.
        """

        if plot is None:
            plot = self.__plotModel
        if scan is None:
            scan = self.__scan

        key = self.objectName()

        def imageChannels(plotModel, scan):
            """Iterate through all channel scan from image items"""
            for item in plotModel.items():
                if isinstance(item, plot_item_model.ImageItem):
                    channelRef = item.imageChannel()
                    if channelRef is None:
                        continue
                    channel = channelRef.channel(scan)
                    if channel is None:
                        continue
                    yield channel

        # Remove preferences from the previous plot
        if previousPlot is not None and scan is not None:
            for channel in imageChannels(previousPlot, scan):
                channel.setPreferedRefreshRate(key, None)

        if plot is None:
            return

        # Remove preferences from the previous scan
        if previousScan is not None:
            for channel in imageChannels(plot, previousScan):
                channel.setPreferedRefreshRate(key, None)

        rate = self.__refreshManager.refreshMode()

        if scan is not None:
            # Remove preferences from the prevouos item
            if previousItem is not None:
                item = previousItem
                if isinstance(item, plot_item_model.ImageItem):
                    channelRef = item.imageChannel()
                    if channelRef is not None:
                        channel = channelRef.channel(scan)
                        if channel is not None:
                            channel.setPreferedRefreshRate(key, None)
            elif newItem is not None:
                item = newItem
                if isinstance(item, plot_item_model.ImageItem):
                    channelRef = item.imageChannel()
                    if channelRef is not None:
                        channel = channelRef.channel(scan)
                        if channel is not None:
                            channel.setPreferedRefreshRate(key, rate)
            else:
                # Update the preferences to the current plot and current scan
                for channel in imageChannels(plot, scan):
                    channel.setPreferedRefreshRate(key, rate)

    def __scanStarted(self):
        self.__imageReceived = 0
        self.__createScanRois()
        self.__refreshManager.scanStarted()
        self.__view.scanStarted()
        self.__title.scanStarted(self.__scan)

    def __scanFinished(self):
        self.__refreshManager.scanFinished()
        if self.__imageReceived == 0:
            self.__cleanAll()
        self.__title.scanFinished(self.__scan)

    def __createScanRois(self):
        self.__roiManager.clear()
        if self.__scan is None:
            return

        master = None
        for device in self.__scan.devices():
            if device.name() != self.deviceName():
                continue
            if device.master() and device.master().isMaster():
                master = device
                break

        if master is None:
            return

        for device in self.__scan.devices():
            if not device.isChildOf(master):
                continue

            roi = device.metadata().roi
            if roi is None:
                continue

            if isinstance(roi, lima_rois.RoiProfile):
                # Must be checked first as a RoiProfile is a RectRoi
                if roi.mode == "vertical":
                    item = flint_rois.LimaVProfileRoi()
                elif roi.mode == "horizontal":
                    item = flint_rois.LimaHProfileRoi()
                else:
                    item = silx_rois.RectangleROI()
                origin = roi.x, roi.y
                size = roi.width, roi.height
                self.__roiManager.addRoi(item)
                item.setGeometry(origin=origin, size=size)
            elif isinstance(roi, lima_rois.Roi):
                item = silx_rois.RectangleROI()
                origin = roi.x, roi.y
                size = roi.width, roi.height
                self.__roiManager.addRoi(item)
                item.setGeometry(origin=origin, size=size)
            elif isinstance(roi, lima_rois.ArcRoi):
                item = silx_rois.ArcROI()
                center = roi.cx, roi.cy
                self.__roiManager.addRoi(item)
                item.setGeometry(
                    center=center,
                    innerRadius=roi.r1,
                    outerRadius=roi.r2,
                    startAngle=numpy.deg2rad(roi.a1),
                    endAngle=numpy.deg2rad(roi.a2),
                )
            else:
                item = None
            if item is not None:
                item.setName(device.name())
                item.setEditable(False)
                item.setSelectable(False)
                item.setColor(qt.QColor(0x80, 0x80, 0x80))
                item.setVisible(False)

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
            elif isinstance(item, plot_item_model.RoiItem):
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
        if plotModel is None or self.__scan is None:
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
        if isinstance(item, plot_item_model.ImageItem):
            self.__updateImageItem(item)
        elif isinstance(item, plot_item_model.RoiItem):
            roi_name = item.roiName()
            roi = [r for r in self.__roiManager.getRois() if r.getName() == roi_name]
            roi = roi[0] if len(roi) > 0 else None
            if roi is not None:
                roi.setVisible(item.isVisible())

    def __updateImageItem(self, item: plot_model.Item):
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
        colormap = model_helper.getColormapFromItem(item, style, self.__colormap)

        live = self.flintModel().liveWindow()
        if live is not None:
            colormapWidget = live.ownedColormapWidget(self)
        else:
            colormapWidget = None

        if style.symbolStyle is style_model.SymbolStyle.NO_SYMBOL:
            if image.ndim == 3:
                imageItem = plot_helper.FlintImageRgba()
                if colormapWidget is not None:
                    colormapWidget.setItem(None)
            else:
                imageItem = plot_helper.FlintImage()
                imageItem.setColormap(colormap)
                if colormapWidget is not None:
                    colormapWidget.setItem(imageItem)
            imageItem.setData(image, copy=False)
            imageItem.setCustomItem(item)
            imageItem.setScan(scan)
            imageItem.setName(legend)
            self.__plot.addItem(imageItem)

            self.__plot._setActiveItem("image", legend)
            plotItems.append(_ItemDescription(legend, "image", image.shape))
            self.__title.itemUpdated(scan, item)

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
