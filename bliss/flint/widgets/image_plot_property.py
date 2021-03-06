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
import weakref

from silx.gui import qt

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from bliss.flint.utils import qt_backport
from . import delegates
from . import _property_tree_helper


_logger = logging.getLogger(__name__)


class _DataItem(_property_tree_helper.ScanRowItem):
    def __init__(self):
        super(_DataItem, self).__init__()
        self.__used = delegates.HookedStandardItem("")
        self.__displayed = delegates.HookedStandardItem("")
        self.__style = qt.QStandardItem("")
        self.__remove = qt.QStandardItem("")

        self.__plotModel: Optional[plot_model.Plot] = None
        self.__plotItem: Optional[plot_model.Item] = None
        self.__channel: Optional[scan_model.Channel] = None
        self.__device: Optional[scan_model.Device] = None
        self.__treeView: Optional[qt.QTreeView] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

        self.setOtherRowItems(
            self.__used, self.__displayed, self.__style, self.__remove
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

    def __usedChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            # There is a plot item already
            assert self.__plotModel is not None
            self.__plotModel.removeItem(self.__plotItem)
        else:
            assert self.__channel is not None
            assert self.__plotModel is not None
            plot = self.__plotModel

            with plot.transaction():
                items = list(plot.items())
                for i in items:
                    plot.removeItem(i)
                channelName = self.__channel.name()
                newItem = plot_item_model.ImageItem(plot)
                newItem.setImageChannel(plot_model.ChannelRef(plot, channelName))
                plot.addItem(newItem)

            self.__plotItem = newItem

    def __visibilityViewChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            state = item.data(delegates.VisibilityRole)
            self.__plotItem.setVisible(state == qt.Qt.Checked)

    def setDevice(self, device: scan_model.Device):
        self.__device = device
        self.setDeviceLookAndFeel(device)
        self.__used.setCheckable(False)

        if device.type() == scan_model.DeviceType.VIRTUAL_ROI:
            state = qt.Qt.Unchecked
            self.__displayed.modelUpdated = None
            self.__displayed.setData(state, role=delegates.VisibilityRole)
            self.__displayed.modelUpdated = weakref.WeakMethod(
                self.__visibilityViewChanged
            )
            if self.__treeView.isPersistentEditorOpen(self.__displayed.index()):
                self.__treeView.closePersistentEditor(self.__displayed.index())
            self.__treeView.openPersistentEditor(self.__displayed.index())

    def device(self):
        return self.__device

    def setChannel(self, channel: scan_model.Channel):
        self.__channel = channel
        self.setChannelLookAndFeel(channel)
        self.__used.modelUpdated = None
        self.__used.setCheckable(True)
        self.__used.modelUpdated = weakref.WeakMethod(self.__usedChanged)

    def setPlotItem(self, plotItem):
        self.__plotItem = plotItem

        isRoiItem = isinstance(plotItem, plot_item_model.RoiItem)

        if not isRoiItem:
            self.__used.modelUpdated = None
            self.__used.setData(plotItem, role=delegates.PlotItemRole)
            self.__used.setCheckState(qt.Qt.Checked)
            self.__used.modelUpdated = weakref.WeakMethod(self.__usedChanged)

            self.__style.setData(plotItem, role=delegates.PlotItemRole)
            self.__style.setData(self.__flintModel, role=delegates.FlintModelRole)
            self.__remove.setData(plotItem, role=delegates.PlotItemRole)

        if plotItem is not None:
            isVisible = plotItem.isVisible()
            state = qt.Qt.Checked if isVisible else qt.Qt.Unchecked
            self.__displayed.modelUpdated = None
            self.__displayed.setData(state, role=delegates.VisibilityRole)
            self.__displayed.modelUpdated = weakref.WeakMethod(
                self.__visibilityViewChanged
            )
        else:
            self.__displayed.modelUpdated = None
            self.__displayed.setData(None, role=delegates.VisibilityRole)

        if self.__channel is None:
            self.setPlotItemLookAndFeel(plotItem)

        if self.__treeView.isPersistentEditorOpen(self.__displayed.index()):
            self.__treeView.closePersistentEditor(self.__displayed.index())
        self.__treeView.openPersistentEditor(self.__displayed.index())
        if not isRoiItem:
            self.__treeView.openPersistentEditor(self.__remove.index())
            if self.__treeView.isPersistentEditorOpen(self.__style.index()):
                self.__treeView.closePersistentEditor(self.__style.index())
            self.__treeView.openPersistentEditor(self.__style.index())
        # FIXME: why do we have to do that?
        self.__treeView.resizeColumnToContents(self.__style.column())


class ImagePlotPropertyWidget(qt.QWidget):

    NameColumn = 0
    UseColumn = 1
    VisibleColumn = 2
    StyleColumn = 3
    RemoveColumn = 4

    def __init__(self, parent=None):
        super(ImagePlotPropertyWidget, self).__init__(parent=parent)
        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__plotModel: Optional[plot_model.Plot] = None

        self.__tree = qt_backport.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__visibilityDelegate = delegates.VisibilityPropertyItemDelegate(self)
        self.__removeDelegate = delegates.RemovePropertyItemDelegate(self)
        self.__styleDelegate = delegates.StyleItemDelegate(self, editable=False)

        model = qt.QStandardItemModel(self)
        self.__tree.setModel(model)

        self.__focusWidget = None

        self.__tree.setFrameShape(qt.QFrame.NoFrame)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.__tree)

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        self.__flintModel = flintModel

    def focusWidget(self):
        return self.__focusWidget

    def setFocusWidget(self, widget):
        if self.__focusWidget is not None:
            widget.plotModelUpdated.disconnect(self.__plotModelUpdated)
            widget.scanModelUpdated.disconnect(self.__currentScanChanged)
        self.__focusWidget = widget
        if self.__focusWidget is not None:
            widget.plotModelUpdated.connect(self.__plotModelUpdated)
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
        self.__plotModel = plotModel
        if self.__plotModel is not None:
            self.__plotModel.structureChanged.connect(self.__structureChanged)
            self.__plotModel.itemValueChanged.connect(self.__itemValueChanged)
        self.__updateTree()

    def __currentScanChanged(self, scanModel):
        self.__setScan(scanModel)

    def __structureChanged(self):
        self.__updateTree()

    def __itemValueChanged(
        self, item: plot_model.Item, eventType: plot_model.ChangeEventType
    ):
        pass

    def plotModel(self) -> Union[None, plot_model.Plot]:
        return self.__plotModel

    def __setScan(self, scan):
        self.__scan = scan
        self.__updateTree()

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
        deviceItems: Dict[str, _DataItem] = {}

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
            deviceItems[device.fullName()] = item
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
        for deviceItem in reversed(devices):
            device = deviceItem.device()
            if device.type() == scan_model.DeviceType.VIRTUAL_ROI:
                continue
            if device.type() == scan_model.DeviceType.VIRTUAL_MCA_DETECTOR:
                continue
            if device.name() in ["roi_counters", "roi_profiles"]:
                continue
            if deviceItem not in channelsPerDevices:
                continue
            if channelsPerDevices[deviceItem] > 0:
                continue
            parent = deviceItem.parent()
            if parent is None:
                parent = model
            parent.removeRows(deviceItem.row(), 1)

        return deviceItems, channelItems

    def __updateTree(self):
        # FIXME: expanded/collapsed items have to be restored

        model = self.__tree.model()
        model.clear()

        if self.__plotModel is None:
            model.setHorizontalHeaderLabels([""])
            foo = qt.QStandardItem("")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(
            ["Name", "Use", "Displayed", "Style", "Remove", ""]
        )
        self.__tree.setItemDelegateForColumn(
            self.VisibleColumn, self.__visibilityDelegate
        )
        self.__tree.setItemDelegateForColumn(self.StyleColumn, self.__styleDelegate)
        self.__tree.setItemDelegateForColumn(self.RemoveColumn, self.__removeDelegate)
        header = self.__tree.header()
        header.setSectionResizeMode(self.NameColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.UseColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.VisibleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.StyleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.RemoveColumn, qt.QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(10)
        header.moveSection(self.StyleColumn, self.VisibleColumn)

        scan = self.__scan
        if scan is not None:
            deviceItems, channelItems = self.__genScanTree(
                model, scan, scan_model.ChannelType.IMAGE
            )
        else:
            deviceItems, channelItems = {}, {}

        itemWithoutLocation = qt.QStandardItem("Not linked to this scan")
        model.appendRow(itemWithoutLocation)

        plotImageItems = []

        for plotItem in self.__plotModel.items():
            if isinstance(plotItem, plot_item_model.ImageItem):
                plotImageItems.append(plotItem)
                dataChannel = plotItem.imageChannel()
                if dataChannel is None:
                    continue

                dataChannelName = dataChannel.name()
                if dataChannelName in channelItems:
                    channelItem = channelItems[dataChannelName]
                    channelItem.setPlotItem(plotItem)
                else:
                    item = _DataItem()
                    item.setEnvironment(self.__tree, self.__flintModel)
                    itemWithoutLocation.appendRow(item.rowItems())
                    # It have to be done when model index are initialized
                    item.setPlotItem(plotItem)

            elif isinstance(plotItem, plot_item_model.RoiItem):
                deviceItem = deviceItems.get(plotItem.deviceName())
                if deviceItem is not None:
                    deviceItem.setPlotItem(plotItem)

        if len(plotImageItems) >= 2:
            _logger.warning(
                "More than one image is provided by this plot. A single image is supported, others will be ignored."
            )

        if itemWithoutLocation.rowCount() == 0:
            model.removeRows(itemWithoutLocation.row(), 1)

        self.__tree.expandAll()
