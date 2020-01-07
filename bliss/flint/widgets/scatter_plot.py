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
from typing import Sequence
from typing import Optional

import logging
import numpy

from silx.gui import qt
from silx.gui import icons
from silx.gui.plot.items.shape import BoundingRect
from silx.gui.plot.items.shape import Shape
from silx.gui.plot.items.marker import Marker
from silx.gui.plot.items.scatter import Scatter
from silx.gui.plot.items.curve import Curve

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import style_model
from bliss.flint.model import plot_item_model
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget
from bliss.flint.widgets.plot_helper import FlintPlot
from bliss.flint.helper import scan_info_helper
from bliss.flint.helper import model_helper
from bliss.flint.utils import signalutils
from bliss.flint.widgets import plot_helper


_logger = logging.getLogger(__name__)


class _ManageView(qt.QObject):

    sigZoomMode = qt.Signal(bool)

    def __init__(self, plot):
        super(_ManageView, self).__init__(parent=plot)
        self.__plot = plot
        self.__plot.sigViewChanged.connect(self.__viewChanged)
        self.__inUserView: bool = False

    def __setUserViewMode(self, userMode):
        if self.__inUserView == userMode:
            return
        self.__inUserView = userMode
        self.sigZoomMode.emit(userMode)

    def __viewChanged(self, event):
        if event.userInteraction:
            self.__setUserViewMode(True)

    def scanStarted(self):
        self.__setUserViewMode(False)

    def resetZoom(self):
        self.__plot.resetZoom()
        self.__setUserViewMode(False)

    def plotUpdated(self):
        if not self.__inUserView:
            self.__plot.resetZoom()

    def plotCleared(self):
        self.__plot.resetZoom()
        self.__setUserViewMode(False)

    def createResetZoomAction(self, parent: qt.QWidget) -> qt.QAction:
        resetZoom = qt.QAction(parent)
        resetZoom.triggered.connect(self.resetZoom)
        resetZoom.setText("Reset zoom")
        resetZoom.setToolTip("Back to the auto-zoom")
        resetZoom.setIcon(icons.getQIcon("flint:icons/zoom-auto"))
        resetZoom.setEnabled(self.__inUserView)

        def updateResetZoomAction(isUserMode):
            resetZoom.setEnabled(isUserMode)

        self.sigZoomMode.connect(updateResetZoomAction)

        return resetZoom


class _ScatterPlotItemMixIn:
    def __init__(self):
        self.__plotItem = None

    def customItem(self) -> Optional[plot_item_model.ScatterItem]:
        return self.__plotItem

    def setCustomItem(self, item: plot_item_model.ScatterItem):
        self.__plotItem = item


class _MainScatter(Scatter, _ScatterPlotItemMixIn):
    def __init__(self):
        Scatter.__init__(self)
        _ScatterPlotItemMixIn.__init__(self)


class _MainCurve(Curve, _ScatterPlotItemMixIn):
    def __init__(self):
        Curve.__init__(self)
        _ScatterPlotItemMixIn.__init__(self)


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
        self.__plot = FlintPlot(parent=self)
        self.__plot.setActiveCurveStyle(linewidth=2)
        self.__plot.setDataMargins(0.1, 0.1, 0.1, 0.1)
        self.setWidget(self.__plot)
        self.setFocusPolicy(qt.Qt.StrongFocus)
        self.__plot.installEventFilter(self)
        self.__plot.getWidgetHandle().installEventFilter(self)
        self.__view = _ManageView(self.__plot)

        toolBar = self.__createToolBar()
        self.__plot.addToolBar(toolBar)
        self.__plot.sigMouseMoved.connect(self.__onMouseMove)
        self.__plot.sigMouseLeft.connect(self.__onMouseLeft)

        self.__syncAxisTitle = signalutils.InvalidatableSignal(self)
        self.__syncAxisTitle.triggered.connect(self.__updateAxesLabel)
        self.__syncAxis = signalutils.InvalidatableSignal(self)
        self.__syncAxis.triggered.connect(self.__scatterAxesUpdated)

        self.__toolTipMarker = Marker()
        self.__toolTipMarker._setLegend("marker-tooltip")
        self.__toolTipMarker.setColor("pink")
        self.__toolTipMarker.setSymbol("+")
        self.__toolTipMarker.setSymbolSize(8)
        self.__toolTipMarker.setVisible(False)

        self.__bounding = BoundingRect()
        self.__bounding._setLegend("bound")
        _logger.warning("Add initial bound")

        self.__lastValue = Scatter()
        self.__lastValue.setSymbol(",")
        self.__lastValue._setLegend("scatter")
        self.__lastValue.setVisible(False)
        self.__lastValue.setZValue(10)
        self.__rect = Shape("rectangle")
        self.__rect._setLegend("rect")
        self.__rect.setVisible(False)
        self.__rect.setFill(False)
        self.__rect.setColor("#E0E0E0")
        self.__rect.setZValue(0.1)

        self.__aggregator = signalutils.EventAggregator()

        self.__permanentItems = [
            self.__bounding,
            self.__toolTipMarker,
            self.__lastValue,
            self.__rect,
        ]

        for o in self.__permanentItems:
            self.__plot._add(o)

        self.__updater = qt.QTimer(self)
        self.__updater.timeout.connect(self.__update)
        self.__updater.start(500)

    def __update(self):
        if self.__aggregator.empty():
            return
        _logger.debug("Update widget")
        self.__aggregator.flush()

    def __onMouseMove(self, event: plot_helper.MouseMovedEvent):
        mouseButton = qt.QApplication.mouseButtons()
        if mouseButton == qt.Qt.NoButton:
            self.__updateTooltip(event.xPixel, event.yPixel)
        else:
            # Avoid to display the tooltip if the user is doing stuffs
            self.__updateTooltip(None, None)

    def __onMouseLeft(self):
        self.__updateTooltip(None, None)

    def __updateTooltip(self, x, y):
        plot = self.__plot

        # Start from top-most item
        result = None
        if x is not None:
            for result in plot.pickItems(
                x, y, lambda item: isinstance(item, _ScatterPlotItemMixIn)
            ):
                # Break at the first result
                break

        if result is not None:
            # Get last index
            # with matplotlib it should be the top-most point
            index = result.getIndices(copy=False)[-1]
            item = result.getItem()
            x = item.getXData(copy=False)[index]
            y = item.getYData(copy=False)[index]
            value = item.getValueData(copy=False)[index]

            assert isinstance(item, _ScatterPlotItemMixIn)
            plotItem = item.customItem()
            if plotItem is not None:
                assert (
                    plotItem.xChannel() is not None
                    and plotItem.yChannel() is not None
                    and plotItem.valueChannel() is not None
                )
                xName = plotItem.xChannel().displayName(self.__scan)
                yName = plotItem.yChannel().displayName(self.__scan)
                vName = plotItem.valueChannel().displayName(self.__scan)
            else:
                xName = "X"
                yName = "Y"
                vName = "Value"

            colormap = item.getColormap()
            # FIXME: This should be merged to Silx
            vmin, vmax = colormap.getColormapRange(item.getValueData(copy=False))
            colors = colormap.applyToData(numpy.array([value, vmin, vmax]))
            cssColor = f"#{colors[0,0]:02X}{colors[0,1]:02X}{colors[0,2]:02X}"

            text = f"""<html><ul>
            <li><b>Index:</b> {index}</li>
            <li><b>{xName}:</b> {x}</li>
            <li><b>{yName}:</b> {y}</li>
            <li><b>{vName}:</b> <font color="{cssColor}">■</font> {value}</li>
            </ul></html>"""
            self.__updateToolTipMarker(x, y)
            cursorPos = qt.QCursor.pos() + qt.QPoint(10, 10)
            qt.QToolTip.showText(cursorPos, text, self.__plot)
        else:
            self.__updateToolTipMarker(None, None)
            qt.QToolTip.hideText()

    def __updateToolTipMarker(self, x, y):
        if x is None:
            self.__toolTipMarker.setVisible(False)
        else:
            self.__toolTipMarker.setVisible(True)
            self.__toolTipMarker.setPosition(x, y)

    def __createToolBar(self):
        toolBar = qt.QToolBar(self)

        from silx.gui.plot.actions import mode
        from silx.gui.plot.actions import control

        toolBar.addAction(mode.ZoomModeAction(self.__plot, self))
        toolBar.addAction(mode.PanModeAction(self.__plot, self))

        resetZoom = self.__view.createResetZoomAction(parent=self)
        toolBar.addAction(resetZoom)
        toolBar.addSeparator()

        # Axis
        toolBar.addAction(plot_helper.CustomAxisAction(self.__plot, self))
        action = control.CrosshairAction(self.__plot, parent=self)
        action.setIcon(icons.getQIcon("flint:icons/crosshair"))
        toolBar.addAction(action)
        toolBar.addAction(control.GridAction(self.__plot, "major", self))
        toolBar.addSeparator()

        # Tools
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
        # FIXME implement that
        action = qt.QAction(self)
        action.setText("Profile")
        action.setToolTip("Manage the profiles to this scatter (not yet implemented)")
        icon = icons.getQIcon("flint:icons/profile")
        action.setIcon(icon)
        action.setEnabled(False)
        toolBar.addAction(action)

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
                xAxis.add(item.xChannel().channel(scan))
                yAxis.add(item.yChannel().channel(scan))
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

        _logger.warning("Update bound %s", bound)
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
        self.__redrawAll()

    def __clear(self):
        self.__items = {}
        self.__plot.clear()
        _logger.warning("Add bound after clear")
        for o in self.__permanentItems:
            self.__plot._add(o)

    def __scanStarted(self):
        self.__view.scanStarted()
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

        if ymeta.axesPoints is not None and xmeta.axesPoints is not None:
            scatter.setVisualizationParameter(
                scatter.VisualizationParameter.GRID_SHAPE,
                (ymeta.axesPoints, xmeta.axesPoints),
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

        if xmeta.axesKind is not None and ymeta.axesKind is not None:
            if (
                xmeta.axesKind == scan_model.AxesKind.FAST
                or ymeta.axesKind == scan_model.AxesKind.SLOW
            ):
                order = "row"
            if (
                xmeta.axesKind == scan_model.AxesKind.SLOW
                or ymeta.axesKind == scan_model.AxesKind.FAST
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

        pointBased = True
        if style.fillStyle is not style_model.FillStyle.NO_FILL:
            pointBased = False
            fillStyle = style.fillStyle
            scatter = _MainScatter()
            scatter.setData(x=xx, y=yy, value=value, copy=False)
            scatter.setColormap(colormap)
            scatter.setCustomItem(item)
            key = legend + "_solid"
            scatter._setLegend(key)
            plot._add(scatter)
            if fillStyle == style_model.FillStyle.SCATTER_REGULAR_GRID:
                scatter.setVisualization(scatter.Visualization.REGULAR_GRID)
            elif fillStyle == style_model.FillStyle.SCATTER_IRREGULAR_GRID:
                scatter.setVisualization(scatter.Visualization.IRREGULAR_GRID)

                # FIXME: This have to be removed at one point
                fast = model_helper.getFastChannel(xChannel, yChannel)
                if fast is not None:
                    fastMetadata = fast.metadata()
                    assert fastMetadata is not None
                    axesPoints = fastMetadata.axesPoints
                    if axesPoints is not None:
                        if len(xx) < axesPoints * 2:
                            # The 2 first lines have to be displayed
                            xxx, yyy, vvv = xx, yy, value
                        elif len(xx) % axesPoints != 0:
                            # Last line have to be displayed
                            extra = slice(len(xx) - len(xx) % axesPoints, len(xx))
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
            self.__lastValue.setVisible(True)
        else:
            self.__lastValue.setVisible(False)

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
            symbolColormap = colormap if style.symbolColor is None else None
            if pointBased and symbolColormap:
                symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
                if symbolStyle == " ":
                    symbolStyle = "o"
                scatter = _MainScatter()
                scatter.setData(x=xx, y=yy, value=value, copy=False)
                scatter.setColormap(symbolColormap)
                scatter.setSymbol(symbolStyle)
                scatter.setSymbolSize(style.symbolSize)
                scatter.setCustomItem(item)
                key = legend + "_point"
                scatter._setLegend(key)
                plot._add(scatter)
                plotItems.append((key, "scatter"))
        elif style.symbolStyle is not style_model.SymbolStyle.NO_SYMBOL:
            symbolStyle = style_model.symbol_to_silx(style.symbolStyle)
            curve = _MainCurve()
            curve.setData(x=xx, y=yy, copy=False)
            curve.setColor(style.symbolColor)
            curve.setSymbol(symbolStyle)
            curve.setLineStyle(" ")
            curve.setSymbolSize(style.symbolSize)
            curve.setCustomItem(item)
            key = legend + "_point"
            curve._setLegend(key)
            plot._add(curve)
            plotItems.append((key, "curve"))

        self.__items[item] = plotItems
        self.__updatePlotZoom(updateZoomNow)

    def __updatePlotZoom(self, updateZoomNow):
        if updateZoomNow:
            self.__view.plotUpdated()
        else:
            self.__plotWasUpdated = True
