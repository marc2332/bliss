# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Tuple
from typing import Dict
from typing import List
from typing import Sequence
from typing import Optional

import logging
import numpy

from silx.gui import qt
from silx.gui import icons
from silx.gui import colors
from silx.gui.plot.actions import histogram
from silx.gui.plot.items.shape import BoundingRect
from silx.gui.plot.items.shape import Shape
from silx.gui.plot.items.scatter import Scatter
from silx.gui.plot.items.curve import Curve

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from bliss.flint.utils import signalutils
from .utils import plot_helper
from .utils import view_helper
from .utils import refresh_helper
from .utils import tooltip_helper
from .utils import marker_action
from .utils import export_action
from .utils import profile_action
from .utils import plot_action
from .utils import style_action


_logger = logging.getLogger(__name__)


class _Title:
    def __init__(self, plot):
        self.__plot = plot

        self.__hasPreviousImage: bool = False
        """Remember that there was an image before this scan, to avoid to
        override the title at startup and waiting for the first image"""
        self.__lastSubTitle = None
        """Remembers the last subtitle in case it have to be reuse when
        displaying the data from the previous scan"""

    def itemUpdated(
        self, scan, item: plot_model.Item, normalization: ScatterNormalization
    ):
        self.__updateAll(scan, item, normalization)

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

    def __formatItemTitle(
        self,
        scan: scan_model.Scan,
        item: plot_item_model.ScatterItem = None,
        normalization: ScatterNormalization = None,
    ):
        if item is None:
            return None

        valueChannel = item.valueChannel()
        if valueChannel is not None:
            title = valueChannel.baseName()
            size = normalization.size()
            if size is not None:
                height, width = size
                title = f"{title}: {width} × {height}"
        else:
            title = "No data"

        groups = {}

        groupByChannels = item.groupByChannels()
        if groupByChannels is not None:
            for channel in groupByChannels:
                channel = channel.channel(scan)
                if channel is None:
                    continue
                array = channel.array()
                if array is None or len(array) == 0:
                    continue
                fvalue = array[-1]
                groups[channel.name()] = fvalue

        if len(groups) > 0:
            titles = [f"{k} = {v}" for k, v in groups.items()]
            frame = ", ".join(titles)
            title = f"{title} {frame}"
        return title

    def __updateTitle(self, title):
        subtitle = None
        if self.__lastSubTitle is not None:
            subtitle = self.__lastSubTitle
        if subtitle is not None:
            title = f"{title}\n{subtitle}"
        self.__plot.setGraphTitle(title)

    def __updateAll(
        self,
        scan: scan_model.Scan,
        item: plot_model.Item = None,
        normalization: ScatterNormalization = None,
    ):
        title = scan_info_helper.get_full_title(scan)
        subtitle = None
        itemTitle = self.__formatItemTitle(scan, item, normalization)
        self.__lastSubTitle = itemTitle
        if itemTitle is not None:
            subtitle = f"{itemTitle}"
        if subtitle is not None:
            title = f"{title}\n{subtitle}"
        self.__plot.setGraphTitle(title)


class ScatterNormalization:
    """Transform raw scatter data into displayable normalized scatter"""

    def __init__(self, scan: scan_model.Scan, item: plot_model.Item, scatterSize: int):

        # Normalize backnforth into regular image
        channel = item.xChannel().channel(scan)
        scatter = scan.getScatterDataByChannel(channel)
        self.__axisKind: List[scan_model.AxisKind] = []
        self.__indexes = None
        self.__skipImage = False
        if scatter:
            for axisId in range(scatter.maxDim()):
                channel = scatter.channelsAt(axisId)[0]
                kind = channel.metadata().axisKind
                self.__axisKind.append(kind)
            shape = scatter.shape()
            self.__nbmin = numpy.prod([(1 if i in [-1, None] else i) for i in shape])

            kinds = set(self.__axisKind)
            hasNone = None in kinds
            hasForth = scan_model.AxisKind.FORTH in kinds
            hasBacknforth = scan_model.AxisKind.BACKNFORTH in kinds
            _hasStep = scan_model.AxisKind.STEP in kinds

            isForth = hasForth and not hasNone and not hasBacknforth
            isBacknforth = not isForth and not hasNone

            if isBacknforth:
                if scatterSize % self.__nbmin == 0:
                    size = scatterSize
                else:
                    size = scatterSize + (self.__nbmin - scatterSize)

                indexes = numpy.arange(size, dtype=int)

                try:
                    indexes.shape = shape
                    # Compute the index transformation to revert
                    # backnforth into a regular image
                    # Use numpy order
                    self.__axisKind = list(reversed(self.__axisKind))
                    for i in reversed(range(len(self.__axisKind))):
                        kind = self.__axisKind[i]
                        if kind == scan_model.AxisKind.BACKNFORTH:
                            indexes.shape = (-1,) + shape[i:]
                            indexes[1::2, :] = indexes[1::2, ::-1]
                    self.__indexes = indexes.flatten()
                except Exception:
                    # There could be a lot of inconsistencies with meta info
                    self.__skipImage = True

        xChannel = item.xChannel().channel(scan)
        yChannel = item.yChannel().channel(scan)
        self.__size = None
        if xChannel is not None and yChannel is not None:
            xmeta = xChannel.metadata()
            ymeta = yChannel.metadata()
            if ymeta.axisPoints is not None and xmeta.axisPoints is not None:
                self.__size = ymeta.axisPoints, xmeta.axisPoints

        # Filter to display the last frame
        groupByChannels = item.groupByChannels()
        if groupByChannels is not None:
            mask = numpy.array([True] * scatterSize)
            for channel in groupByChannels:
                channel = channel.channel(scan)
                if channel is None:
                    continue
                array = channel.array()
                if array is None or len(array) == 0:
                    continue
                fvalue = array[-1]
                mask = numpy.logical_and(mask, array == fvalue)
            self.__mask = mask

            if self.__indexes is not None:
                self.__skipImage = True
                self.__indexes = None
        else:
            self.__mask = None

        if self.__indexes is not None:
            self.__max = numpy.nanmax(self.__indexes) + 1

    def hasNormalization(self) -> bool:
        return self.__indexes is not None or self.__mask is not None

    def normalize(self, array: numpy.ndarray) -> numpy.ndarray:
        if array is None:
            return None
        if len(array) == 0:
            return array

        # Normalize backnforth into regular image
        if self.__indexes is not None:
            extraSize = self.__max - len(array)
            if extraSize > 0:
                array = numpy.append(array, [numpy.nan] * extraSize)
            return array[self.__indexes]

        # Only display last frame
        if self.__mask is None:
            return array
        return array[self.__mask]

    def size(self) -> Optional[Tuple[int, int]]:
        """Returns the size of the scatter if it's a regular scatter

        Else return None
        """
        return self.__size

    def setupScatterItem(
        self,
        scatter: Scatter,
        xChannel: scan_model.Channel,
        yChannel: scan_model.Channel,
    ):
        """Feed the scatter plot item with metadata from the channels to
        optimize the rendering"""
        xmeta = xChannel.metadata()
        ymeta = yChannel.metadata()

        if (
            not self.__skipImage
            and ymeta.axisPoints is not None
            and xmeta.axisPoints is not None
        ):
            scatter.setVisualizationParameter(
                scatter.VisualizationParameter.GRID_SHAPE,
                (ymeta.axisPoints, xmeta.axisPoints),
            )

        if (
            xmeta.start is not None
            and xmeta.stop is not None
            and ymeta.start is not None
            and ymeta.stop is not None
        ):
            scatter.setVisualizationParameter(
                scatter.VisualizationParameter.GRID_BOUNDS,
                ((xmeta.start, ymeta.start), (xmeta.stop, ymeta.stop)),
            )

        initialized = False
        hasAxisPoints = (
            xmeta.axisPointsHint is not None and ymeta.axisPointsHint is not None
        )
        hasAxisPointsHint = (
            xmeta.axisPoints is not None and ymeta.axisPoints is not None
        )

        if xmeta.axisKind is not None and ymeta.axisKind is not None:
            if xmeta.axisId < ymeta.axisId:
                order = "row"
            elif xmeta.axisId > ymeta.axisId:
                order = "column"

            scatter.setVisualizationParameter(
                scatter.VisualizationParameter.GRID_MAJOR_ORDER, order
            )
            initialized = True

        if self.__skipImage or hasAxisPointsHint or (hasAxisPoints and not initialized):
            width, height = xmeta.axisPointsHint, ymeta.axisPointsHint
            if width is None:
                width = xmeta.axisPoints
            if height is None:
                height = ymeta.axisPoints
            if height is not None and width is not None:
                scatter.setVisualizationParameter(
                    scatter.VisualizationParameter.BINNED_STATISTIC_SHAPE,
                    (height, width),
                )
            if (
                xmeta.start is not None
                and xmeta.stop is not None
                and ymeta.start is not None
                and ymeta.stop is not None
            ):
                xrange = min(xmeta.start, xmeta.stop), max(xmeta.start, xmeta.stop)
                yrange = min(ymeta.start, ymeta.stop), max(ymeta.start, ymeta.stop)
                if width > 1 and height > 1:
                    x_half_px = abs(xmeta.start - xmeta.stop) / (width - 1) * 0.5
                    y_half_px = abs(ymeta.start - ymeta.stop) / (height - 1) * 0.5
                    xrange = xrange[0] - x_half_px, xrange[1] + x_half_px
                    yrange = yrange[0] - y_half_px, yrange[1] + y_half_px

                scatter.setVisualizationParameter(
                    scatter.VisualizationParameter.DATA_BOUNDS_HINT, (yrange, xrange)
                )

    def isImageRenderingSupported(
        self, xChannel: scan_model.Channel, yChannel: scan_model.Channel
    ):
        """True if there is enough metadata to display this 2 axis as an image.

        The scatter data also have to be structured in order to display it.
        """
        if self.__skipImage:
            return False
        if self.__indexes is not None:
            return True
        xmeta = xChannel.metadata()
        ymeta = yChannel.metadata()
        if xmeta.axisKind != scan_model.AxisKind.FORTH:
            return False
        if ymeta.axisKind != scan_model.AxisKind.FORTH:
            return False
        return set([xmeta.axisId, ymeta.axisId]) == set([0, 1])

    def isHistogramingRenderingSupported(
        self, xChannel: scan_model.Channel, yChannel: scan_model.Channel
    ):
        """True if there is enough metadata to display this 2 axis as an
        histogram.
        """
        xmeta = xChannel.metadata()
        ymeta = yChannel.metadata()
        if xmeta.axisPoints is None and xmeta.axisPointsHint is None:
            return False
        if ymeta.axisPoints is None and ymeta.axisPointsHint is None:
            return False
        return True


class ScatterPlotWidget(plot_helper.PlotWidget):
    def __init__(self, parent=None):
        super(ScatterPlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[Tuple[str, str]]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = plot_helper.FlintPlot(parent=self)
        self.__plot.sigMousePressed.connect(self.__onPlotPressed)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setDataMargins(0.05, 0.05, 0.05, 0.05)

        self.__colormap = colors.Colormap("viridis")

        self.__title = _Title(self.__plot)

        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__view = view_helper.ViewManager(self.__plot)

        self.__aggregator = plot_helper.ScalarEventAggregator(self)
        self.__refreshManager = refresh_helper.RefreshManager(self)
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

        self.__tooltipManager = tooltip_helper.TooltipItemManager(self, self.__plot)
        self.__tooltipManager.setFilter(plot_helper.FlintScatter)

        self.__syncAxisTitle = signalutils.InvalidatableSignal(self)
        self.__syncAxisTitle.triggered.connect(self.__updateAxesLabel)
        self.__syncAxis = signalutils.InvalidatableSignal(self)
        self.__syncAxis.triggered.connect(self.__scatterAxesUpdated)

        self.__bounding = BoundingRect()
        self.__bounding.setName("bound")

        self.__lastValue = Scatter()
        self.__lastValue.setSymbol(",")
        self.__lastValue.setName("cursor_last_value")
        self.__lastValue.setVisible(False)
        self.__lastValue.setZValue(10)
        self.__rect = Shape("rectangle")
        self.__rect.setName("rect")
        self.__rect.setVisible(False)
        self.__rect.setFill(False)
        self.__rect.setColor("#E0E0E0")
        self.__rect.setZValue(0.1)

        self.__plot.addItem(self.__bounding)
        self.__plot.addItem(self.__tooltipManager.marker())
        self.__plot.addItem(self.__lastValue)
        self.__plot.addItem(self.__rect)

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
                if isinstance(item, plot_helper.FlintScatter):
                    colormapWidget.setItem(item)
                    break
            else:
                colormapWidget.setColormap(self.__colormap)

    def configuration(self):
        config = super(ScatterPlotWidget, self).configuration()
        try:
            config.colormap = self.__colormap._toDict()
        except Exception:
            # As it relies on private API, make it safe
            _logger.error("Impossible to save colormap preference", exc_info=True)
        return config

    def setConfiguration(self, config):
        if config.colormap is not None:
            try:
                self.__colormap._setFromDict(config.colormap)
            except Exception:
                # As it relies on private API, make it safe
                _logger.error(
                    "Impossible to restore colormap preference", exc_info=True
                )
        super(ScatterPlotWidget, self).setConfiguration(config)

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
        toolBar.addAction(
            plot_action.CustomAxisAction(self.__plot, self, kind="scatter")
        )
        toolBar.addSeparator()

        # Item
        action = style_action.FlintItemStyleAction(self.__plot, self)
        toolBar.addAction(action)
        self.__styleAction = action
        action = style_action.FlintSharedColormapAction(self.__plot, self)
        action.setInitColormapWidgetCallback(self.__initColormapWidget)
        toolBar.addAction(action)
        self.__contrastAction = action
        toolBar.addSeparator()

        # Tools
        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)

        action = histogram.PixelIntensitiesHistoAction(self.__plot, self)
        icon = icons.getQIcon("flint:icons/histogram")
        action.setIcon(icon)
        toolBar.addAction(action)

        toolBar.addAction(profile_action.ProfileAction(self.__plot, self, "scatter"))

        action = marker_action.MarkerAction(
            plot=self.__plot, parent=self, kind="scatter"
        )
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

    def __onPlotPressed(self):
        self.widgetActivated.emit(self)

    def createPropertyWidget(self, parent: qt.QWidget):
        from . import scatter_plot_property

        propertyWidget = scatter_plot_property.ScatterPlotPropertyWidget(parent)
        propertyWidget.setFlintModel(self.__flintModel)
        propertyWidget.setFocusWidget(self)
        return propertyWidget

    def flintModel(self) -> Optional[flint_model.FlintState]:
        return self.__flintModel

    def setFlintModel(self, flintModel: Optional[flint_model.FlintState]):
        self.__flintModel = flintModel
        self.__exportAction.setFlintModel(flintModel)
        self.__styleAction.setFlintModel(flintModel)
        self.__contrastAction.setFlintModel(flintModel)

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
        self.__sanitizeItems()
        self.__redrawAll()
        self.__syncAxisTitle.trigger()
        self.__syncAxis.trigger()

    def plotModel(self) -> plot_model.Plot:
        return self.__plotModel

    def __structureChanged(self):
        self.__redrawAll()
        self.__syncAxisTitle.trigger()
        self.__syncAxis.trigger()

    def __transactionFinished(self):
        if self.__plotWasUpdated:
            self.__plotWasUpdated = False
            self.__view.plotUpdated()
        self.__syncAxisTitle.validate()
        self.__syncAxis.validate()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        inTransaction = self.__plotModel.isInTransaction()
        if eventType == plot_model.ChangeEventType.VISIBILITY:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.CUSTOM_STYLE:
            self.__updateItem(item)
        elif eventType == plot_model.ChangeEventType.X_CHANNEL:
            self.__sanitizeItem(item)
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
            self.__syncAxis.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.Y_CHANNEL:
            self.__sanitizeItem(item)
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
            self.__syncAxis.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.VALUE_CHANNEL:
            self.__sanitizeItem(item)
            self.__updateItem(item)

    def __scatterAxesUpdated(self):
        scan = self.__scan
        plot = self.__plotModel
        if plot is None:
            bound = None
        else:
            xAxis = set([])
            yAxis = set([])
            for item in plot.items():
                xChannel = item.xChannel()
                yChannel = item.yChannel()
                if xChannel is not None:
                    xAxis.add(xChannel.channel(scan))
                if yChannel is not None:
                    yAxis.add(yChannel.channel(scan))
            xAxis.discard(None)
            yAxis.discard(None)

            def getRange(axis: Sequence[scan_model.Channel]):
                vv = set([])
                for a in axis:
                    metadata = a.metadata()
                    v = set([metadata.start, metadata.stop, metadata.min, metadata.max])
                    vv.update(v)
                vv.discard(None)
                if len(vv) == 0:
                    return None, None
                return min(vv), max(vv)

            xRange = getRange(list(xAxis))
            yRange = getRange(list(yAxis))
            if xRange[0] is None or yRange[0] is None:
                bound = None
            else:
                bound = (xRange[0], xRange[1], yRange[0], yRange[1])

        self.__bounding.setBounds(bound)

        if bound is not None:
            self.__rect.setVisible(True)
            self.__rect.setPoints([(xRange[0], yRange[0]), (xRange[1], yRange[1])])
        else:
            self.__rect.setVisible(False)

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
                if not item.isVisible():
                    continue
                if isinstance(item, plot_item_model.ScatterItem):
                    xLabels.append(item.xChannel().displayName(scan))
                    yLabels.append(item.yChannel().displayName(scan))
            xLabel = " + ".join(sorted(set(xLabels)))
            yLabel = " + ".join(sorted(set(yLabels)))
        self.__plot.getXAxis().setLabel(xLabel)
        self.__plot.getYAxis().setLabel(yLabel)

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
        self.__title.scanRemoved(self.__scan)
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
                self.__title.scanStarted(self.__scan)

        self.scanModelUpdated.emit(scan)
        self.__sanitizeItems()
        self.__redrawAll()

    def __scanStarted(self):
        self.__refreshManager.scanStarted()
        if self.__flintModel is not None and self.__flintModel.getDate() == "0214":
            self.__lastValue.setSymbol("\u2665")
        else:
            self.__lastValue.setSymbol(",")
        self.__markerAction.clear()
        self.__lastValue.setData(x=[], y=[], value=[])
        self.__lastValue.setVisible(True)
        self.__view.scanStarted()
        self.__syncAxis.trigger()
        self.__title.scanStarted(self.__scan)

    def __scanFinished(self):
        self.__refreshManager.scanFinished()
        self.__lastValue.setVisible(False)
        self.__title.scanFinished(self.__scan)

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
        self.__rect.setVisible(False)
        self.__lastValue.setVisible(False)
        self.__view.plotCleared()

    def __cleanItem(self, item: plot_model.Item) -> bool:
        itemKeys = self.__items.pop(item, [])
        if len(itemKeys) == 0:
            return False
        for key in itemKeys:
            self.__plot.remove(*key)
        return True

    def __redrawAll(self):
        self.__cleanAll()
        plotModel = self.__plotModel
        if plotModel is None:
            return

        for item in plotModel.items():
            self.__updateItem(item)

    def __sanitizeItems(self):
        scan = self.__scan
        if scan is None:
            return
        plot = self.__plotModel
        if plot is None:
            return
        for item in plot.items():
            if isinstance(item, plot_item_model.ScatterItem):
                self.__sanitizeItem(item)

    def __sanitizeItem(self, item: plot_item_model.ScatterItem):
        if not item.isValid():
            return
        if not isinstance(item, plot_item_model.ScatterItem):
            return

        xChannelRef = item.xChannel()
        yChannelRef = item.yChannel()
        if xChannelRef is None or yChannelRef is None:
            return

        scan = self.__scan
        assert scan is not None
        xChannel = xChannelRef.channel(scan)
        yChannel = yChannelRef.channel(scan)
        if xChannel is None or yChannel is None:
            return

        if xChannel.metadata().group != yChannel.metadata().group:
            # FIXME: This should be cached... Try to display data not from the same group
            return

        scatterData = scan.getScatterDataByChannel(xChannel)
        if scatterData is None:
            # FIXME: This should be cached... Try to display data not from the same group
            return

        if scatterData.maxDim() <= 2:
            # Nothing to do
            return

        # Now we have to find groupBy
        xId = scatterData.channelAxis(xChannel)
        yId = scatterData.channelAxis(yChannel)
        if xId == yId:
            # FIXME: This should not be displayed anyway
            _logger.warning("ndim scatter using same axis dim for the 2 axis")
            return

        # Try to find channels to group together other dimensions
        axisIds = list(range(scatterData.maxDim()))
        axisIds.remove(xId)
        axisIds.remove(yId)
        groupBys = [scatterData.findGroupableAt(i) for i in axisIds]
        if None in groupBys:
            # FIXME: Should not be displayed
            _logger.warning("ndim scatter can't be grouped to 2d scatter")
            return

        groupByRefs = [plot_model.ChannelRef(item, c.name()) for c in groupBys]
        item.setGroupByChannels(groupByRefs)

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

        valueChannel = item.valueChannel()
        xChannel = item.xChannel()
        yChannel = item.yChannel()
        if valueChannel is None or xChannel is None or yChannel is None:
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        # Channels from channel ref
        xChannel = xChannel.channel(scan)
        yChannel = yChannel.channel(scan)

        value = valueChannel.array(scan)
        xx = xChannel.array()
        yy = yChannel.array()
        if value is None or xx is None or yy is None:
            if wasUpdated:
                self.__updatePlotZoom(updateZoomNow)
            return

        # FIXME: This have to be cached and optimized
        scatterSize = len(xx)
        normalization = ScatterNormalization(scan, item, scatterSize)
        if normalization.hasNormalization():
            xx = normalization.normalize(xx)
            yy = normalization.normalize(yy)
            value = normalization.normalize(value)
            indexes = numpy.arange(scatterSize)
            indexes = normalization.normalize(indexes)
        else:
            indexes = None

        self.__title.itemUpdated(scan, item, normalization)

        legend = valueChannel.name()
        style = item.getStyle(scan)
        colormap = model_helper.getColormapFromItem(item, style, self.__colormap)

        scatter = None
        curve = None
        pointBased = True
        if style.fillStyle is not style_model.FillStyle.NO_FILL:
            pointBased = False
            fillStyle = style.fillStyle
            scatter = plot_helper.FlintScatter()
            scatter.setData(x=xx, y=yy, value=value, copy=False)
            scatter.setRealIndexes(indexes)
            scatter.setColormap(colormap)
            scatter.setCustomItem(item)
            scatter.setScan(scan)
            key = legend + "_solid"
            scatter.setName(key)

            if fillStyle == style_model.FillStyle.SCATTER_INTERPOLATION:
                scatter.setVisualization(scatter.Visualization.SOLID)
            elif normalization.isImageRenderingSupported(xChannel, yChannel):
                if fillStyle == style_model.FillStyle.SCATTER_REGULAR_GRID:
                    scatter.setVisualization(scatter.Visualization.REGULAR_GRID)
                elif fillStyle == style_model.FillStyle.SCATTER_IRREGULAR_GRID:
                    scatter.setVisualization(scatter.Visualization.IRREGULAR_GRID)
            elif normalization.isHistogramingRenderingSupported(xChannel, yChannel):
                # Fall back with an histogram
                scatter.setVisualization(scatter.Visualization.BINNED_STATISTIC)
            else:
                pointBased = True

            if not pointBased:
                plot.addItem(scatter)
                normalization.setupScatterItem(scatter, xChannel, yChannel)
                plotItems.append((key, "scatter"))

        if not pointBased and len(value) >= 1:
            vmin, vmax = colormap.getColormapRange(value)
            colormap2 = colormap.copy()
            colormap2.setVRange(vmin, vmax)
            self.__lastValue.setData(x=xx[-1:], y=yy[-1:], value=value[-1:])
            self.__lastValue.setColormap(colormap2)

        if style.lineStyle == style_model.LineStyle.SCATTER_SEQUENCE:
            key = plot.addCurve(
                x=xx,
                y=yy,
                legend=legend + "_line",
                color=style.lineColor,
                linestyle="-",
                resetzoom=False,
            )
            plotItems.append((key, "curve"))

        if pointBased:
            symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
            if symbolStyle == " ":
                symbolStyle = "o"
            scatter = plot_helper.FlintScatter()
            scatter.setData(x=xx, y=yy, value=value, copy=False)
            scatter.setRealIndexes(indexes)
            scatter.setColormap(colormap)
            scatter.setSymbol(symbolStyle)
            scatter.setSymbolSize(style.symbolSize)
            scatter.setCustomItem(item)
            scatter.setScan(scan)
            key = legend + "_point"
            scatter.setName(key)
            plot.addItem(scatter)
            plotItems.append((key, "scatter"))
        elif (
            style.symbolStyle is not style_model.SymbolStyle.NO_SYMBOL
            and style.symbolColor is not None
        ):
            symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
            curve = Curve()
            curve.setData(x=xx, y=yy, copy=False)
            curve.setColor(style.symbolColor)
            curve.setSymbol(symbolStyle)
            curve.setLineStyle(" ")
            curve.setSymbolSize(style.symbolSize)
            key = legend + "_point"
            curve.setName(key)
            plot.addItem(curve)
            plotItems.append((key, "curve"))

        live = self.flintModel().liveWindow()
        if live is not None:
            colormapWidget = live.ownedColormapWidget(self)
        else:
            colormapWidget = None

        if scatter is not None:
            # Profile is not selectable,
            # so it does not interfere with profile interaction
            scatter._setSelectable(False)
            self.__plot._setActiveItem("scatter", scatter.getLegend())
        elif curve is not None:
            self.__plot._setActiveItem("curve", curve.getLegend())

        if colormapWidget is not None:
            if scatter is not None:
                colormapWidget.setItem(scatter)
            else:
                colormapWidget.setItem(None)

        self.__items[item] = plotItems
        self.__updatePlotZoom(updateZoomNow)

    def __updatePlotZoom(self, updateZoomNow):
        if updateZoomNow:
            self.__view.plotUpdated()
        else:
            self.__plotWasUpdated = True
