# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
from typing import List
from typing import Dict
from typing import Optional

import logging

from silx.gui import qt
from silx.gui import icons
from silx.gui import utils as qtutils

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model
from bliss.flint.model import scan_model
from bliss.flint.helper import model_helper
from bliss.flint.utils import qmodelutils
from . import delegates
from . import _property_tree_helper


_logger = logging.getLogger(__name__)


class YAxesEditor(qt.QWidget):

    valueChanged = qt.Signal()

    def __init__(self, parent=None):
        qt.QWidget.__init__(self, parent=parent)
        self.setContentsMargins(1, 1, 1, 1)
        self.__plotItem = None
        layout = qt.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.__group = qt.QButtonGroup(self)

        y1Check = qt.QRadioButton(self)
        y1Check.setObjectName("y1")
        y2Check = qt.QRadioButton(self)
        y2Check.setObjectName("y2")

        self.__group.addButton(y1Check)
        self.__group.addButton(y2Check)
        self.__group.setExclusive(True)
        self.__group.buttonClicked[qt.QAbstractButton].connect(self.__checkedChanged)

        layout.addWidget(y1Check)
        layout.addWidget(y2Check)

    def __getY1Axis(self):
        return self.findChildren(qt.QRadioButton, "y1")[0]

    def __getY2Axis(self):
        return self.findChildren(qt.QRadioButton, "y2")[0]

    def yAxis(self) -> str:
        if self.__getY1Axis().isChecked():
            return "left"
        elif self.__getY2Axis().isChecked():
            return "right"
        return ""

    def setPlotItem(self, plotItem):
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.disconnect(self.__plotItemChanged)
        self.__plotItem = plotItem
        if self.__plotItem is not None:
            self.__plotItem.valueChanged.connect(self.__plotItemChanged)
            self.__plotItemYAxisChanged()

        isReadOnly = self.__isReadOnly()

        w = self.__getY1Axis()
        w.setEnabled(not isReadOnly)

        w = self.__getY2Axis()
        w.setEnabled(not isReadOnly)

        self.__updateToolTips()

    def __isReadOnly(self):
        if self.__plotItem is None:
            return False
        return not isinstance(self.__plotItem, plot_item_model.CurveMixIn)

    def __updateToolTips(self):
        isReadOnly = self.__isReadOnly()

        w = self.__getY1Axis()
        if w.isChecked():
            w.setToolTip("Displayed within the Y1 axis")
        elif isReadOnly:
            w.setToolTip("")
        else:
            w.setToolTip("Display it within the Y1 axis")

        w = self.__getY2Axis()
        if w.isChecked():
            w.setToolTip("Displayed within the Y2 axis")
        elif isReadOnly:
            w.setToolTip("")
        else:
            w.setToolTip("Display it within the Y2 axis")

    def __checkedChanged(self, button: qt.QRadioButton):
        yAxis1 = self.__getY1Axis()
        yAxis2 = self.__getY2Axis()
        if button is yAxis1:
            axis = "left"
        elif button is yAxis2:
            axis = "right"
        else:
            assert False
        if self.__plotItem is not None:
            self.__plotItem.setYAxis(axis)
        self.valueChanged.emit()

    def __plotItemChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.YAXIS:
            self.__plotItemYAxisChanged()

    def __plotItemYAxisChanged(self):
        try:
            axis = self.__plotItem.yAxis()
        except Exception:
            _logger.error(
                "Error while reaching y-axis from %s", self.__plotItem, exc_info=True
            )
            axis = None

        y1Axis = self.__getY1Axis()
        old = y1Axis.blockSignals(True)
        y1Axis.setChecked(axis == "left")
        y1Axis.blockSignals(old)

        y2Axis = self.__getY2Axis()
        old = y2Axis.blockSignals(True)
        y2Axis.setChecked(axis == "right")
        y2Axis.blockSignals(old)

        self.__updateToolTips()


class YAxesPropertyItemDelegate(qt.QStyledItemDelegate):

    YAxesRole = qt.Qt.UserRole + 2

    def __init__(self, parent):
        qt.QStyledItemDelegate.__init__(self, parent=parent)

    def createEditor(self, parent, option, index):
        if not index.isValid():
            return super(YAxesPropertyItemDelegate, self).createEditor(
                parent, option, index
            )

        editor = YAxesEditor(parent=parent)
        plotItem = self.getPlotItem(index)
        editor.setPlotItem(plotItem)
        if plotItem is None:
            editor.valueChanged.connect(self.__editorsChanged)

        editor.setMinimumSize(editor.sizeHint())
        editor.setMaximumSize(editor.sizeHint())
        editor.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Fixed)
        return editor

    def __editorsChanged(self):
        editor = self.sender()
        self.commitData.emit(editor)

    def getPlotItem(self, index) -> Union[None, plot_model.Item]:
        plotItem = index.data(delegates.PlotItemRole)
        if not isinstance(plotItem, plot_model.Item):
            return None
        return plotItem

    def setEditorData(self, editor, index):
        plotItem = self.getPlotItem(index)
        editor.setPlotItem(plotItem)

    def setModelData(self, editor, model, index):
        plotItem = self.getPlotItem(index)
        if plotItem is None:
            yAxis = editor.yAxis()
            model.setData(index, yAxis, role=self.YAxesRole)
        else:
            # Already up-to-date
            # From signals from plot items
            pass

    def updateEditorGeometry(self, editor, option, index):
        # Center the widget to the cell
        size = editor.sizeHint()
        half = size / 2
        halfPoint = qt.QPoint(half.width(), half.height() - 1)
        pos = option.rect.center() - halfPoint
        editor.move(pos)


class _AddItemAction(qt.QWidgetAction):
    def __init__(self, parent: qt.QObject):
        assert isinstance(parent, CurvePlotPropertyWidget)
        super(_AddItemAction, self).__init__(parent)
        parent.plotItemSelected.connect(self.__selectionChanged)

        widget = qt.QToolButton(parent)
        icon = icons.getQIcon("flint:icons/add-item")
        widget.setIcon(icon)
        widget.setAutoRaise(True)
        widget.setToolTip("CReate new items in the plot")
        widget.setPopupMode(qt.QToolButton.InstantPopup)
        widget.setEnabled(False)
        widget.setText("Create items")
        self.setDefaultWidget(widget)

        menu = qt.QMenu(parent)
        menu.aboutToShow.connect(self.__aboutToShow)
        widget.setMenu(menu)

    def __aboutToShow(self):
        menu: qt.QMenu = self.sender()
        menu.clear()

        item = self.parent().selectedPlotItem()
        if isinstance(item, plot_item_model.CurveMixIn):
            menu.addSection("Statistics")

            action = qt.QAction(self)
            action.setText("Max marker")
            icon = icons.getQIcon("flint:icons/item-stats")
            action.setIcon(icon)
            action.triggered.connect(self.__createMax)
            menu.addAction(action)

            action = qt.QAction(self)
            action.setText("Min marker")
            icon = icons.getQIcon("flint:icons/item-stats")
            action.setIcon(icon)
            action.triggered.connect(self.__createMin)
            menu.addAction(action)

            menu.addSection("Functions")

            action = qt.QAction(self)
            action.setText("Derivative function")
            icon = icons.getQIcon("flint:icons/item-func")
            action.setIcon(icon)
            action.triggered.connect(self.__createDerivative)
            menu.addAction(action)

            action = qt.QAction(self)
            action.setText("Gaussian fit")
            icon = icons.getQIcon("flint:icons/item-func")
            action.setIcon(icon)
            action.triggered.connect(self.__createGaussianFit)
            menu.addAction(action)
        else:
            action = qt.QAction(self)
            action.setText("No available items")
            action.setEnabled(False)
            menu.addAction(action)

    def __selectionChanged(self, current: plot_model.Item):
        self.defaultWidget().setEnabled(current is not None)

    def __createMax(self):
        parentItem = self.parent().selectedPlotItem()
        if parentItem is not None:
            plot = parentItem.plot()
            newItem = plot_state_model.MaxCurveItem(plot)
            newItem.setSource(parentItem)
            with plot.transaction():
                plot.addItem(newItem)

    def __createMin(self):
        parentItem = self.parent().selectedPlotItem()
        if parentItem is not None:
            plot = parentItem.plot()
            newItem = plot_state_model.MinCurveItem(plot)
            newItem.setSource(parentItem)
            with plot.transaction():
                plot.addItem(newItem)

    def __createDerivative(self):
        parentItem = self.parent().selectedPlotItem()
        if parentItem is not None:
            plot = parentItem.plot()
            newItem = plot_state_model.DerivativeItem(plot)
            newItem.setSource(parentItem)
            with plot.transaction():
                plot.addItem(newItem)

    def __createGaussianFit(self):
        parentItem = self.parent().selectedPlotItem()
        if parentItem is not None:
            plot = parentItem.plot()
            newItem = plot_state_model.GaussianFitItem(plot)
            newItem.setSource(parentItem)
            with plot.transaction():
                plot.addItem(newItem)


class _DataItem(_property_tree_helper.ScanRowItem):
    def __init__(self):
        super(_DataItem, self).__init__()
        qt.QStandardItem.__init__(self)
        self.__xaxis = delegates.HookedStandardItem("")
        self.__yaxes = delegates.HookedStandardItem("")
        self.__displayed = delegates.HookedStandardItem("")
        self.__style = qt.QStandardItem("")
        self.__remove = qt.QStandardItem("")
        self.__error = qt.QStandardItem("")
        self.__xAxisSelected = False

        self.__plotModel: Optional[plot_model.Plot] = None
        self.__plotItem: Optional[plot_model.Item] = None
        self.__channel: Optional[scan_model.Channel] = None
        self.__treeView: Optional[qt.QTreeView] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

        self.setOtherRowItems(
            self.__xaxis,
            self.__yaxes,
            self.__displayed,
            self.__style,
            self.__remove,
            self.__error,
        )

    def __hash__(self):
        return hash(id(self))

    def channel(self) -> Optional[scan_model.Channel]:
        return self.__channel

    def setEnvironment(
        self, treeView: qt.QTreeView, flintState: flint_model.FlintState
    ):
        self.__treeView = treeView
        self.__flintModel = flintState

    def setPlotModel(self, plotModel: plot_model.Plot):
        self.__plotModel = plotModel

    def plotModel(self) -> Optional[plot_model.Plot]:
        return self.__plotModel

    def axesItem(self) -> qt.QStandardItem:
        return self.__yaxes

    def styleItem(self) -> qt.QStandardItem:
        return self.__style

    def updateError(self):
        scan = self.__flintModel.currentScan()
        if scan is None or self.__plotItem is None:
            # No message to reach
            self.__error.setText(None)
            self.__error.setIcon(qt.QIcon())
            return
        result = self.__plotItem.getErrorMessage(scan)
        if result is None:
            # Ths item is valid
            self.__error.setText(None)
            self.__error.setIcon(qt.QIcon())
            return

        self.__error.setText(result)
        icon = icons.getQIcon("flint:icons/warning")
        self.__error.setIcon(icon)

    def __yAxisChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            # There is a plot item already
            return
        else:
            assert self.__channel is not None
            assert self.__plotModel is not None
            plot = self.__plotModel
            yAxis = item.data(role=YAxesPropertyItemDelegate.YAxesRole)
            assert yAxis in ["left", "right"]

            curve, wasUpdated = model_helper.createCurveItem(
                plot, self.__channel, yAxis
            )
            if wasUpdated:
                # It's now an item with a value
                self.setPlotItem(curve)

    def __visibilityViewChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            state = item.data(delegates.VisibilityRole)
            self.__plotItem.setVisible(state == qt.Qt.Checked)

    def setSelectedXAxis(self):
        if self.__xAxisSelected:
            return
        self.__xAxisSelected = True

        old = self.__xaxis.modelUpdated
        self.__xaxis.modelUpdated = None
        try:
            self.__xaxis.setData(qt.Qt.Checked, role=delegates.RadioRole)
        finally:
            self.__xaxis.modelUpdated = old
        # It have to be closed to be refreshed. Sounds like a bug.
        self.__treeView.closePersistentEditor(self.__xaxis.index())
        self.__treeView.openPersistentEditor(self.__xaxis.index())

    def __xAxisChanged(self, item: qt.QStandardItem):
        assert self.__channel is not None
        assert self.__plotModel is not None

        # Reach the top master
        topMaster = self.__channel.device().topMaster()
        scan = topMaster.scan()

        # Reach all plot items from this top master
        curves = model_helper.reachAllCurveItemFromDevice(
            self.__plotModel, scan, topMaster
        )

        if len(curves) == 0:
            # Create an item to store the x-value
            plot = self.__plotModel
            channelName = self.__channel.name()
            newItem = plot_item_model.CurveItem(plot)
            newItem.setXChannel(plot_model.ChannelRef(plot, channelName))
            plot.addItem(newItem)
        else:
            # Update the x-channel of all this curves
            with self.__plotModel.transaction():
                xChannelName = self.__channel.name()
                for curve in curves:
                    xChannel = plot_model.ChannelRef(curve, xChannelName)
                    curve.setXChannel(xChannel)

    def setDevice(self, device: scan_model.Device):
        self.setDeviceLookAndFeel(device)
        self.__updateXAxisStyle(True, None)

    def __rootRow(self) -> int:
        item = self
        while item is not None:
            parent = item.parent()
            if parent is None:
                break
            item = parent
        return item.row()

    def __updateXAxisStyle(self, setAxisValue: bool, radioValue=None):
        # FIXME: avoid hard coded style
        cellColors = [qt.QColor(0xE8, 0xE8, 0xE8), qt.QColor(0xF5, 0xF5, 0xF5)]
        old = self.__xaxis.modelUpdated
        self.__xaxis.modelUpdated = None
        if setAxisValue:
            self.__xaxis.setData(radioValue, role=delegates.RadioRole)
        i = self.__rootRow()
        self.__xaxis.setBackground(cellColors[i % 2])
        self.__xaxis.modelUpdated = old

    def setChannel(self, channel: scan_model.Channel):
        assert self.__treeView is not None
        self.__channel = channel
        self.setChannelLookAndFeel(channel)
        self.__updateXAxisStyle(True, qt.Qt.Unchecked)
        self.__xaxis.modelUpdated = self.__xAxisChanged
        self.__yaxes.modelUpdated = self.__yAxisChanged

        self.__treeView.openPersistentEditor(self.__xaxis.index())
        self.__treeView.openPersistentEditor(self.__yaxes.index())

    def data(self, role=qt.Qt.DisplayRole):
        if role == qt.Qt.ToolTipRole:
            return self.toolTip()
        return _property_tree_helper.ScanRowItem.data(self, role)

    def toolTip(self):
        if self.__channel is not None:
            data = self.__channel.data()
            if data is not None:
                array = data.array()
            else:
                array = None
            if array is None:
                shape = "No data"
            elif array is tuple():
                shape = "Scalar"
            else:
                shape = " × ".join([str(s) for s in array.shape])
            name = self.__channel.name()
            return f"""<html><ul>
            <li><b>Channel name:</b> {name}</li>
            <li><b>Data shape:</b> {shape}</li>
            </ul></html>"""

        return None

    def plotItem(self) -> Optional[plot_model.Item]:
        return self.__plotItem

    def setPlotItem(self, plotItem):
        self.__plotItem = plotItem

        self.__yaxes.setData(plotItem, role=delegates.PlotItemRole)
        self.__style.setData(plotItem, role=delegates.PlotItemRole)
        self.__remove.setData(plotItem, role=delegates.PlotItemRole)

        self.__yaxes.modelUpdated = self.__yAxisChanged

        if plotItem is not None:
            isVisible = plotItem.isVisible()
            state = qt.Qt.Checked if isVisible else qt.Qt.Unchecked
            self.__displayed.setData(state, role=delegates.VisibilityRole)
            self.__displayed.modelUpdated = self.__visibilityViewChanged
        else:
            self.__displayed.setData(None, role=delegates.VisibilityRole)
            self.__displayed.modelUpdated = None

        if self.__channel is None:
            self.setPlotItemLookAndFeel(plotItem)

        if isinstance(plotItem, plot_item_model.CurveItem):
            self.__xaxis.modelUpdated = self.__xAxisChanged
            useXAxis = True
        elif isinstance(plotItem, plot_item_model.CurveMixIn):
            # self.__updateXAxisStyle(False, None)
            useXAxis = False
            self.__updateXAxisStyle(False)
        elif isinstance(plotItem, plot_state_model.CurveStatisticItem):
            useXAxis = False
            self.__updateXAxisStyle(False)

        # FIXME: It have to be converted into delegate
        if useXAxis:
            self.__treeView.openPersistentEditor(self.__xaxis.index())
        # FIXME: close/open is needed, sometime the item is not updated
        self.__treeView.closePersistentEditor(self.__yaxes.index())
        self.__treeView.openPersistentEditor(self.__yaxes.index())
        self.__treeView.openPersistentEditor(self.__displayed.index())
        self.__treeView.openPersistentEditor(self.__remove.index())
        widget = delegates.StylePropertyWidget(self.__treeView)
        widget.setPlotItem(self.__plotItem)
        widget.setFlintModel(self.__flintModel)
        self.__treeView.setIndexWidget(self.__style.index(), widget)

        self.updateError()


class CurvePlotPropertyWidget(qt.QWidget):

    NameColumn = 0
    XAxisColumn = 1
    YAxesColumn = 2
    VisibleColumn = 3
    StyleColumn = 4
    RemoveColumn = 5

    plotItemSelected = qt.Signal(object)

    def __init__(self, parent=None):
        super(CurvePlotPropertyWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__plotModel: Union[None, plot_model.Plot] = None
        self.__tree = qt.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__xAxisInvalidated: bool = False
        self.__xAxisDelegate = delegates.RadioPropertyItemDelegate(self)
        self.__yAxesDelegate = YAxesPropertyItemDelegate(self)
        self.__visibilityDelegate = delegates.VisibilityPropertyItemDelegate(self)
        self.__removeDelegate = delegates.RemovePropertyItemDelegate(self)

        model = qt.QStandardItemModel(self)
        self.__tree.setModel(model)
        selectionModel = self.__tree.selectionModel()
        selectionModel.currentChanged.connect(self.__selectionChanged)

        self.__scan = None
        self.__focusWidget = None

        toolBar = self.__createToolBar()

        self.__tree.setFrameShape(qt.QFrame.NoFrame)
        line = qt.QFrame(self)
        line.setFrameShape(qt.QFrame.HLine)
        line.setFrameShadow(qt.QFrame.Sunken)

        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolBar)
        layout.addWidget(line)
        layout.addWidget(self.__tree)

    def __removeAllItems(self):
        if self.__plotModel is None:
            return
        with self.__plotModel.transaction():
            items = list(self.__plotModel.items())
            for item in items:
                try:
                    self.__plotModel.removeItem(item)
                except IndexError:
                    # Item was maybe already removed
                    pass

    def __createToolBar(self):
        toolBar = qt.QToolBar(self)
        toolBar.setMovable(False)
        action = _AddItemAction(self)
        toolBar.addAction(action)

        action = qt.QAction(self)
        icon = icons.getQIcon("flint:icons/remove-all-items")
        action.setIcon(icon)
        action.setToolTip("Remove all the items from the plot")
        action.triggered.connect(self.__removeAllItems)
        toolBar.addAction(action)
        return toolBar

    def __findItemFromPlotItem(
        self, requestedItem: plot_model.Item
    ) -> Optional[_DataItem]:
        """Returns a silx plot item from a flint plot item."""
        if requestedItem is None:
            return None
        model = self.__tree.model()
        for index in qmodelutils.iterAllItems(model):
            item = model.itemFromIndex(index)
            if isinstance(item, _DataItem):
                plotItem = item.plotItem()
                if plotItem is requestedItem:
                    return item
        return None

    def __selectionChangedFromPlot(self, current: plot_model.Item):
        self.selectPlotItem(current)

    def selectPlotItem(self, select: plot_model.Item):
        selectionModel = self.__tree.selectionModel()
        if select is None:
            # Break reentrant signals
            indices = selectionModel.selectedRows()
            index = indices[0] if len(indices) > 0 else qt.QModelIndex()
            if index.isValid():
                selectionModel.select(qt.QModelIndex(), qt.QItemSelectionModel.Clear)
            return
        if select is self.selectedPlotItem():
            # Break reentrant signals
            return
        item = self.__findItemFromPlotItem(select)
        flags = qt.QItemSelectionModel.Rows | qt.QItemSelectionModel.ClearAndSelect
        if item is None:
            index = qt.QModelIndex()
        else:
            index = item.index()
        selectionModel = self.__tree.selectionModel()
        selectionModel.select(index, flags)

    def __selectionChanged(self, current: qt.QModelIndex, previous: qt.QModelIndex):
        model = self.__tree.model()
        index = model.index(current.row(), 0, current.parent())
        item = model.itemFromIndex(index)
        if isinstance(item, _DataItem):
            plotItem = item.plotItem()
        else:
            plotItem = None
        self.plotItemSelected.emit(plotItem)

    def selectedPlotItem(self) -> Optional[plot_model.Item]:
        """Returns the current selected plot item, if one"""
        selectionModel = self.__tree.selectionModel()
        indices = selectionModel.selectedRows()
        index = indices[0] if len(indices) > 0 else qt.QModelIndex()
        if not index.isValid():
            return None
        model = self.__tree.model()
        index = model.index(index.row(), 0, index.parent())
        item = model.itemFromIndex(index)
        if isinstance(item, _DataItem):
            plotItem = item.plotItem()
            return plotItem
        return None

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        self.__flintModel = flintModel

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):
        if self.__focusWidget is not None:
            widget.plotModelUpdated.disconnect(self.__plotModelUpdated)
            widget.plotItemSelected.disconnect(self.__selectionChangedFromPlot)
            widget.scanModelUpdated.disconnect(self.__currentScanChanged)
        self.__focusWidget = widget
        if self.__focusWidget is not None:
            widget.plotModelUpdated.connect(self.__plotModelUpdated)
            widget.plotItemSelected.connect(self.__selectionChangedFromPlot)
            widget.scanModelUpdated.connect(self.__currentScanChanged)
            plotModel = widget.plotModel()
            scanModel = widget.scan()
        else:
            plotModel = None
            scanModel = None
        self.__plotModelUpdated(plotModel)
        self.__currentScanChanged(scanModel)

    def __plotModelUpdated(self, plotModel):
        self.setPlotModel(plotModel)

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
        self.__updateTree()

    def __currentScanChanged(self, scanModel):
        self.__setScan(scanModel)

    def __structureChanged(self):
        self.__updateTree()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        assert self.__plotModel is not None
        if eventType == plot_model.ChangeEventType.X_CHANNEL:
            if self.__plotModel.isInTransaction():
                self.__xAxisInvalidated = True
            else:
                self.__updateTree()

    def __transactionFinished(self):
        if self.__xAxisInvalidated:
            self.__xAxisInvalidated = False
            self.__updateTree()

    def plotModel(self) -> Union[None, plot_model.Plot]:
        return self.__plotModel

    def __setScan(self, scan: Optional[scan_model.Scan]):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].disconnect(self.__scanDataUpdated)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].connect(self.__scanDataUpdated)
        self.__updateTree()

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        model = self.__tree.model()
        flags = qt.Qt.MatchWildcard | qt.Qt.MatchRecursive
        items = model.findItems("*", flags)
        channels = set(event.iterUpdatedChannels())
        # FIXME: This loop could be optimized
        for item in items:
            if isinstance(item, _DataItem):
                if item.channel() in channels:
                    item.updateError()

    def __genScanTree(
        self,
        model: qt.QStandardItemModel,
        scan: scan_model.Scan,
        channelFilter: scan_model.ChannelType,
    ) -> Dict[str, _DataItem]:
        """Feed the provided model with a tree of scan concepts (devices,
        channels).

        Returns a map from channel name to Qt items (`_DataItem`)
        """
        assert self.__tree is not None
        assert self.__flintModel is not None
        assert self.__plotModel is not None
        scanTree = {}
        channelItems: Dict[str, _DataItem] = {}

        devices: List[qt.QStandardItem] = []
        channelsPerDevices: Dict[qt.QStandardItem, int] = {}

        for device in scan.devices():
            item = _DataItem()
            item.setEnvironment(self.__tree, self.__flintModel)
            scanTree[device] = item

            master = device.master()
            if master is None:
                # Root device
                parent = model
            else:
                itemMaster = scanTree.get(master, None)
                if itemMaster is None:
                    parent = model
                    _logger.warning("Device list is not well ordered")
                else:
                    parent = itemMaster

            parent.appendRow(item.rowItems())
            # It have to be done when model index are initialized
            item.setDevice(device)
            devices.append(item)

            channels = []
            for channel in device.channels():
                if channel.type() != channelFilter:
                    continue
                channels.append(channel)

            for channel in channels:
                channelItem = _DataItem()
                channelItem.setEnvironment(self.__tree, self.__flintModel)
                item.appendRow(channelItem.rowItems())
                # It have to be done when model index are initialized
                channelItem.setChannel(channel)
                channelItem.setPlotModel(self.__plotModel)
                channelItems[channel.name()] = channelItem

            # Update channel use
            parent = item
            channelsPerDevices[parent] = 0
            while parent is not None:
                if parent in channelsPerDevices:
                    channelsPerDevices[parent] += len(channels)
                parent = parent.parent()
                if parent is None:
                    break

        # Clean up unused devices
        for device in reversed(devices):
            if device not in channelsPerDevices:
                continue
            if channelsPerDevices[device] > 0:
                continue
            parent = device.parent()
            if parent is None:
                parent = model
            parent.removeRows(device.row(), 1)

        return channelItems

    def __updateTree(self):
        collapsed = _property_tree_helper.getPathFromCollapsedNodes(self.__tree)
        selectedItem = self.selectedPlotItem()

        model = self.__tree.model()
        model.clear()

        if self.__plotModel is None:
            model.setHorizontalHeaderLabels([""])
            foo = qt.QStandardItem("")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(
            ["Name", "X", "Y1/Y2", "Displayed", "Style", "Remove", "Message"]
        )
        self.__tree.setItemDelegateForColumn(self.XAxisColumn, self.__xAxisDelegate)
        self.__tree.setItemDelegateForColumn(self.YAxesColumn, self.__yAxesDelegate)
        self.__tree.setItemDelegateForColumn(
            self.VisibleColumn, self.__visibilityDelegate
        )
        self.__tree.setItemDelegateForColumn(self.RemoveColumn, self.__removeDelegate)
        header = self.__tree.header()
        header.setSectionResizeMode(self.NameColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.XAxisColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.YAxesColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.VisibleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.StyleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.RemoveColumn, qt.QHeaderView.ResizeToContents)

        sourceTree: Dict[plot_model.Item, qt.QStandardItem] = {}
        scan = self.__scan
        if scan is not None:
            channelItems = self.__genScanTree(
                model, scan, scan_model.ChannelType.COUNTER
            )
        else:
            channelItems = {}

        itemWithoutLocation = qt.QStandardItem("Not linked to this scan")
        itemWithoutMaster = qt.QStandardItem("Not linked to a master")
        model.appendRow(itemWithoutLocation)
        model.appendRow(itemWithoutMaster)

        xChannelPerMasters = model_helper.getMostUsedXChannelPerMasters(
            scan, self.__plotModel
        )

        for plotItem in self.__plotModel.items():
            parentChannel = None

            if isinstance(plotItem, plot_item_model.ScanItem):
                continue
            if isinstance(plotItem, plot_item_model.MotorPositionMarker):
                continue

            if isinstance(plotItem, plot_model.ComputableMixIn):
                source = plotItem.source()
                if source is None:
                    parent = itemWithoutLocation
                else:
                    itemSource = sourceTree.get(source, None)
                    if itemSource is None:
                        parent = itemWithoutMaster
                        _logger.warning("Item list is not well ordered")
                    else:
                        parent = itemSource
            else:
                if scan is None:
                    parent = itemWithoutLocation
                else:
                    if isinstance(plotItem, plot_item_model.CurveItem):
                        xChannel = plotItem.xChannel()
                        if xChannel is None:
                            yChannel = plotItem.yChannel()
                            if yChannel is not None:
                                yChannelName = yChannel.name()
                                _logger.error(yChannelName)
                                parentChannel = channelItems.get(yChannelName, None)
                                if parentChannel is None:
                                    parent = itemWithoutLocation
                            else:
                                # item with bad content
                                continue
                        else:
                            topMaster = model_helper.getConsistentTopMaster(
                                scan, plotItem
                            )
                            xChannelName = xChannel.name()
                            if (
                                topMaster is not None
                                and xChannelPerMasters[topMaster] == xChannelName
                            ):
                                # The x-channel is what it is expected then we can link the y-channel
                                yChannel = plotItem.yChannel()
                                if yChannel is not None:
                                    yChannelName = yChannel.name()
                                    parentChannel = channelItems[yChannelName]
                                xAxisItem = channelItems[xChannelName]
                                xAxisItem.setSelectedXAxis()
                                if yChannel is None:
                                    # This item must not be displayed
                                    continue
                            else:
                                parent = itemWithoutLocation

            if parentChannel is not None:
                parentChannel.setPlotItem(plotItem)
                sourceTree[plotItem] = parentChannel
            else:
                item = _DataItem()
                item.setEnvironment(self.__tree, self.__flintModel)
                parent.appendRow(item.rowItems())
                # It have to be done when model index are initialized
                item.setPlotItem(plotItem)
                sourceTree[plotItem] = item

        if itemWithoutLocation.rowCount() == 0:
            model.removeRows(itemWithoutLocation.row(), 1)
        if itemWithoutMaster.rowCount() == 0:
            model.removeRows(itemWithoutMaster.row(), 1)

        self.__tree.expandAll()
        _property_tree_helper.collapseNodesFromPaths(self.__tree, collapsed)

        with qtutils.blockSignals(self):
            self.selectPlotItem(selectedItem)
