# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
from typing import List
from typing import Dict
from typing import Optional

import logging

from silx.gui import qt
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.helper import model_helper
from . import delegates
from . import _property_tree_helper


_logger = logging.getLogger(__name__)


class _DataItem(_property_tree_helper.ScanRowItem):
    def __init__(self):
        super(_DataItem, self).__init__()
        self.__xAxis = delegates.HookedStandardItem("")
        self.__yAxis = delegates.HookedStandardItem("")
        self.__valueAxis = delegates.HookedStandardItem("")
        self.__displayed = delegates.HookedStandardItem("")
        self.__style = qt.QStandardItem("")
        self.__remove = qt.QStandardItem("")
        self.__error = qt.QStandardItem("")

        self.__plotModel: Optional[plot_model.Plot] = None
        self.__plotItem: Optional[plot_model.Item] = None
        self.__channel: Optional[scan_model.Channel] = None
        self.__treeView: Optional[qt.QTreeView] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

        self.setOtherRowItems(
            self.__xAxis,
            self.__yAxis,
            self.__valueAxis,
            self.__displayed,
            self.__style,
            self.__remove,
            self.__error,
        )

    def __hash__(self):
        return hash(id(self))

    def setEnvironment(
        self, treeView: qt.QTreeView, flintState: flint_model.FlintState
    ):
        self.__treeView = treeView
        self.__flintModel = flintState

    def setPlotModel(self, plotModel: plot_model.Plot):
        self.__plotModel = plotModel

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

    def __valueAxisChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            # There is a already plot item
            assert self.__plotModel is not None
            plot = self.__plotModel
            model_helper.removeItemAndKeepAxes(plot, self.__plotItem)
        else:
            assert self.__channel is not None
            assert self.__plotModel is not None
            plot = self.__plotModel

            scatter, wasUpdated = model_helper.createScatterItem(plot, self.__channel)
            if wasUpdated:
                # It's now an item with a value
                self.setPlotItem(scatter)

    def __visibilityViewChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            state = item.data(delegates.VisibilityRole)
            self.__plotItem.setVisible(state == qt.Qt.Checked)

    def setSelectedXAxis(self):
        old = self.__xAxis.modelUpdated
        self.__xAxis.modelUpdated = None
        try:
            self.__xAxis.setData(qt.Qt.Checked, role=delegates.RadioRole)
        finally:
            self.__xAxis.modelUpdated = old

    def setSelectedYAxis(self):
        old = self.__yAxis.modelUpdated
        self.__yAxis.modelUpdated = None
        try:
            self.__yAxis.setData(qt.Qt.Checked, role=delegates.RadioRole)
        finally:
            self.__yAxis.modelUpdated = old

    def __xAxisChanged(self, item: qt.QStandardItem):
        assert self.__channel is not None
        assert self.__plotModel is not None
        plot = self.__plotModel

        # Reach all plot items from this top master
        scatters = []
        for item in plot.items():
            if not isinstance(item, plot_item_model.ScatterItem):
                continue
            scatters.append(item)

        channelName = self.__channel.name()
        if len(scatters) == 0:
            # Create an item to store the y-value
            newItem = plot_item_model.ScatterItem(plot)
            newItem.setXChannel(plot_model.ChannelRef(plot, channelName))
            plot.addItem(newItem)
        else:
            # Update the x-channel of all this curves
            with self.__plotModel.transaction():
                for scatter in scatters:
                    channel = plot_model.ChannelRef(scatter, channelName)
                    scatter.setXChannel(channel)

    def __yAxisChanged(self, item: qt.QStandardItem):
        assert self.__channel is not None
        assert self.__plotModel is not None
        plot = self.__plotModel

        # Reach all plot items from this top master
        scatters = []
        for item in plot.items():
            if not isinstance(item, plot_item_model.ScatterItem):
                continue
            scatters.append(item)

        channelName = self.__channel.name()
        if len(scatters) == 0:
            # Create an item to store the y-value
            newItem = plot_item_model.ScatterItem(plot)
            newItem.setYChannel(plot_model.ChannelRef(plot, channelName))
            plot.addItem(newItem)
        else:
            # Update the y-channel of all this curves
            with self.__plotModel.transaction():
                for scatter in scatters:
                    channel = plot_model.ChannelRef(scatter, channelName)
                    scatter.setYChannel(channel)

    def setDevice(self, device: scan_model.Device):
        self.setDeviceLookAndFeel(device)
        self.__xAxis.setData(None, role=delegates.RadioRole)
        self.__yAxis.setData(None, role=delegates.RadioRole)

    def setChannel(self, channel: scan_model.Channel):
        assert self.__treeView is not None
        self.__channel = channel
        self.setChannelLookAndFeel(channel)
        self.__valueAxis.modelUpdated = None
        self.__valueAxis.setCheckable(True)
        self.__valueAxis.modelUpdated = self.__valueAxisChanged

        self.__xAxis.modelUpdated = self.__xAxisChanged
        self.__yAxis.modelUpdated = self.__yAxisChanged
        self.__treeView.openPersistentEditor(self.__yAxis.index())
        self.__treeView.openPersistentEditor(self.__xAxis.index())

    def setPlotItem(self, plotItem):
        self.__plotItem = plotItem

        self.__valueAxis.modelUpdated = None
        self.__valueAxis.setCheckable(True)
        self.__valueAxis.setCheckState(qt.Qt.Checked)
        self.__valueAxis.modelUpdated = self.__valueAxisChanged

        self.__xAxis.modelUpdated = self.__xAxisChanged
        self.__yAxis.modelUpdated = self.__yAxisChanged
        self.__style.setData(plotItem, role=delegates.PlotItemRole)
        self.__remove.setData(plotItem, role=delegates.PlotItemRole)

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

        # FIXME: It have to be converted into delegate
        self.__treeView.openPersistentEditor(self.__xAxis.index())
        self.__treeView.openPersistentEditor(self.__yAxis.index())
        self.__treeView.openPersistentEditor(self.__displayed.index())
        self.__treeView.openPersistentEditor(self.__remove.index())
        widget = delegates.StylePropertyWidget(self.__treeView)
        widget.setPlotItem(self.__plotItem)
        widget.setFlintModel(self.__flintModel)
        self.__treeView.setIndexWidget(self.__style.index(), widget)

        self.updateError()


class ScatterPlotPropertyWidget(qt.QWidget):

    NameColumn = 0
    XAxisColumn = 1
    YAxisColumn = 2
    ValueColumn = 3
    VisibleColumn = 4
    StyleColumn = 4
    RemoveColumn = 6

    def __init__(self, parent=None):
        super(ScatterPlotPropertyWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Union[None, flint_model.FlintState] = None
        self.__plotModel: Union[None, plot_model.Plot] = None
        self.__tree = qt.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__xyAxisInvalidated: bool = False
        self.__xAxisDelegate = delegates.RadioPropertyItemDelegate(self)
        self.__yAxisDelegate = delegates.RadioPropertyItemDelegate(self)
        self.__visibilityDelegate = delegates.VisibilityPropertyItemDelegate(self)
        self.__removeDelegate = delegates.RemovePropertyItemDelegate(self)

        model = qt.QStandardItemModel(self)

        self.__tree.setModel(model)
        self.__scan = None
        self.__focusWidget = None

        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.__tree)

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
            self.__setScan(None)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)
            self.__setScan(self.__flintModel.currentScan())

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):
        if self.__focusWidget is not None:
            widget.plotModelUpdated.disconnect(self.__plotModelUpdated)
        self.__focusWidget = widget
        if self.__focusWidget is not None:
            widget.plotModelUpdated.connect(self.__plotModelUpdated)
            plotModel = widget.plotModel()
        else:
            plotModel = None
        self.__plotModelUpdated(plotModel)

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

    def __currentScanChanged(self):
        self.__setScan(self.__flintModel.currentScan())

    def __structureChanged(self):
        self.__updateTree()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        assert self.__plotModel is not None
        if eventType in [
            plot_model.ChangeEventType.X_CHANNEL,
            plot_model.ChangeEventType.Y_CHANNEL,
        ]:
            if self.__plotModel.isInTransaction():
                self.__xyAxisInvalidated = True
            else:
                self.__updateTree()

    def __transactionFinished(self):
        if self.__xyAxisInvalidated:
            self.__xyAxisInvalidated = False
            self.__updateTree()

    def plotModel(self) -> Union[None, plot_model.Plot]:
        return self.__plotModel

    def __setScan(self, scan: Optional[scan_model.Scan]):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated.disconnect(self.__scanDataUpdated)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanDataUpdated.connect(self.__scanDataUpdated)
        self.__updateTree()

    def __scanDataUpdated(self):
        model = self.__tree.model()
        flags = qt.Qt.MatchWildcard | qt.Qt.MatchRecursive
        items = model.findItems("*", flags)
        # FIXME: This loop could be optimized
        for item in items:
            if isinstance(item, _DataItem):
                item.updateError()

    def __genScanTree(
        self,
        model: qt.QStandardItemModel,
        scan: scan_model.Scan,
        channelFilter: scan_model.ChannelType,
    ) -> Dict[str, _DataItem]:
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
        # FIXME: expanded/collapsed items have to be restored

        model = self.__tree.model()
        model.clear()

        if self.__plotModel is None:
            foo = qt.QStandardItem("Empty")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(
            ["Name", "X", "Y", "Value", "Displayed", "Style", "Remove", "Message"]
        )
        self.__tree.setItemDelegateForColumn(self.YAxisColumn, self.__yAxisDelegate)
        self.__tree.setItemDelegateForColumn(self.XAxisColumn, self.__xAxisDelegate)
        self.__tree.setItemDelegateForColumn(
            self.VisibleColumn, self.__visibilityDelegate
        )
        self.__tree.setItemDelegateForColumn(self.RemoveColumn, self.__removeDelegate)
        header = self.__tree.header()
        header.setSectionResizeMode(self.NameColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.XAxisColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.YAxisColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.ValueColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.VisibleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.StyleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.RemoveColumn, qt.QHeaderView.ResizeToContents)

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

        # FIXME: Here we guess that all the ScatterItems share the x and y
        # channels. If it is not the case, the display will be inconsistent

        for plotItem in self.__plotModel.items():
            parentChannel = None

            if not isinstance(plotItem, plot_item_model.ScatterItem):
                continue

            if scan is None:
                parent = itemWithoutLocation
            else:
                # Update value
                valueChannel = plotItem.valueChannel()
                if valueChannel is not None:
                    channelName = valueChannel.name()
                    parentChannel = channelItems.get(channelName, None)
                    if parentChannel is None:
                        parent = itemWithoutLocation
                    else:
                        # It's fine
                        parentChannel.setPlotItem(plotItem)
                        parent = None
                else:
                    # No value, no new item
                    parent = None

                # Update x-axis selection
                xChannel = plotItem.xChannel()
                if xChannel is not None:
                    xChannelName = xChannel.name()
                    xAxisItem = channelItems.get(xChannelName, None)
                    if xAxisItem is None:
                        # FIXME: It would be good to display something somewhere
                        _logger.warning(
                            "Scatter x-channel '%s' not found in this scan",
                            xChannelName,
                        )
                    else:
                        xAxisItem.setSelectedXAxis()

                # Update y-axis selection
                yChannel = plotItem.yChannel()
                if yChannel is not None:
                    yChannelName = yChannel.name()
                    yAxisItem = channelItems.get(yChannelName, None)
                    if yAxisItem is None:
                        # FIXME: It would be good to display something somewhere
                        _logger.warning(
                            "Scatter y-channel '%s' not found in this scan",
                            xChannelName,
                        )
                    else:
                        yAxisItem.setSelectedYAxis()

            if parent is not None:
                # Recover invalid items in this scan
                item = _DataItem()
                item.setEnvironment(self.__tree, self.__flintModel)
                parent.appendRow(item.rowItems())
                # It have to be done when model index are initialized
                item.setPlotItem(plotItem)

        self.__tree.expandAll()
