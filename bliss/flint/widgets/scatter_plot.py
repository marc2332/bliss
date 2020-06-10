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

from silx.gui import qt
from silx.gui import icons
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


_logger = logging.getLogger(__name__)


class ScatterPlotWidget(plot_helper.PlotWidget):
    def __init__(self, parent=None):
        super(ScatterPlotWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: plot_model.Plot = None

        self.__items: Dict[plot_model.Item, List[Tuple[str, str]]] = {}

        self.__plotWasUpdated: bool = False
        self.__plot = plot_helper.FlintPlot(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setDataMargins(0.05, 0.05, 0.05, 0.05)

        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)
        self.__view = view_helper.ViewManager(self.__plot)

        self.__aggregator = signalutils.EventAggregator(self)
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

        # Tools
        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)
        # FIXME implement that
        action = qt.QAction(self)
        action.setText("Histogram")
        action.setToolTip(
            "Show an histogram of the displayed scatter (not yet implemented)"
        )
        icon = icons.getQIcon("flint:icons/histogram")
        action.setIcon(icon)
        action.setEnabled(False)
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
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
            self.__syncAxis.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.Y_CHANNEL:
            self.__updateItem(item)
            self.__syncAxisTitle.triggerIf(not inTransaction)
            self.__syncAxis.triggerIf(not inTransaction)
        elif eventType == plot_model.ChangeEventType.VALUE_CHANNEL:
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
                    if metadata is None:
                        continue
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
        self.__updateTitle(self.__scan)

    def __updateTitle(self, scan: scan_model.Scan):
        title = scan_info_helper.get_full_title(scan)
        self.__plot.setGraphTitle(title)

    def __scanFinished(self):
        self.__refreshManager.scanFinished()
        self.__lastValue.setVisible(False)

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

    def __optimizeRendering(
        self,
        scatter: Scatter,
        xChannel: scan_model.Channel,
        yChannel: scan_model.Channel,
    ):
        """Feed the scatter plot item with metadata from the channels to
        optimize the rendering"""
        xmeta = xChannel.metadata()
        ymeta = yChannel.metadata()
        if xmeta is None or ymeta is None:
            return

        if ymeta.axisPoints is not None and xmeta.axisPoints is not None:
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

        if xmeta.axisKind is not None and ymeta.axisKind is not None:
            if (
                xmeta.axisKind == scan_model.AxisKind.FAST
                or ymeta.axisKind == scan_model.AxisKind.SLOW
            ):
                order = "row"
            if (
                xmeta.axisKind == scan_model.AxisKind.SLOW
                or ymeta.axisKind == scan_model.AxisKind.FAST
            ):
                order = "column"

            scatter.setVisualizationParameter(
                scatter.VisualizationParameter.GRID_MAJOR_ORDER, order
            )

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

        legend = valueChannel.name()
        style = item.getStyle(scan)
        colormap = model_helper.getColormapFromItem(item, style)

        scatter = None
        curve = None
        pointBased = True
        if style.fillStyle is not style_model.FillStyle.NO_FILL:
            pointBased = False
            fillStyle = style.fillStyle
            scatter = plot_helper.FlintScatter()
            scatter.setData(x=xx, y=yy, value=value, copy=False)
            scatter.setColormap(colormap)
            scatter.setCustomItem(item)
            key = legend + "_solid"
            scatter.setName(key)
            plot.addItem(scatter)
            if fillStyle == style_model.FillStyle.SCATTER_REGULAR_GRID:
                scatter.setVisualization(scatter.Visualization.REGULAR_GRID)
            elif fillStyle == style_model.FillStyle.SCATTER_IRREGULAR_GRID:
                scatter.setVisualization(scatter.Visualization.IRREGULAR_GRID)

                # FIXME: This have to be removed at one point
                fast = model_helper.getFastChannel(xChannel, yChannel)
                if fast is not None:
                    fastMetadata = fast.metadata()
                    assert fastMetadata is not None
                    axisPoints = fastMetadata.axisPoints
                    if axisPoints is not None:
                        if len(xx) < axisPoints * 2:
                            # The 2 first lines have to be displayed
                            xxx, yyy, vvv = xx, yy, value
                        elif len(xx) % axisPoints != 0:
                            # Last line have to be displayed
                            extra = slice(len(xx) - len(xx) % axisPoints, len(xx))
                            xxx, yyy, vvv = xx[extra], yy[extra], value[extra]
                        else:
                            xxx, yyy, vvv = None, None, None
                        if xxx is not None:
                            key2 = plot.addScatter(
                                x=xxx,
                                y=yyy,
                                value=vvv,
                                legend=legend + "_solid2",
                                colormap=colormap,
                                symbol="o",
                                copy=False,
                            )
                            scatter2 = plot.getScatter(key2)
                            scatter2.setSymbolSize(style.symbolSize)
                            plotItems.append((key2, "scatter"))

            elif fillStyle == style_model.FillStyle.SCATTER_INTERPOLATION:
                scatter.setVisualization(scatter.Visualization.SOLID)
            else:
                pointBased = True
            self.__optimizeRendering(scatter, xChannel, yChannel)
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
            scatter.setColormap(colormap)
            scatter.setSymbol(symbolStyle)
            scatter.setSymbolSize(style.symbolSize)
            scatter.setCustomItem(item)
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

        if scatter is not None:
            # Profile is not selectable,
            # so it does not interfere with profile interaction
            scatter._setSelectable(False)
            self.__plot._setActiveItem("scatter", scatter.getLegend())
        elif curve is not None:
            self.__plot._setActiveItem("curve", curve.getLegend())

        self.__items[item] = plotItems
        self.__updatePlotZoom(updateZoomNow)

    def __updatePlotZoom(self, updateZoomNow):
        if updateZoomNow:
            self.__view.plotUpdated()
        else:
            self.__plotWasUpdated = True
