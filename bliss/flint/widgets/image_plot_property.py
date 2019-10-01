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
from typing import Callable
from typing import Optional

import logging

from silx.gui import qt
from silx.gui import icons

from bliss.flint.model import flint_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import scan_model
from . import delegates


_logger = logging.getLogger(__name__)


class _DataItem(qt.QStandardItem):
    def __init__(self, text: str = ""):
        qt.QStandardItem.__init__(self, text)
        self.__used = delegates.HookedStandardItem("")
        self.__displayed = delegates.HookedStandardItem("")
        self.__style = qt.QStandardItem("")
        self.__remove = qt.QStandardItem("")

        icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)
        self.__plotModel: Optional[plot_model.Plot] = None
        self.__plotItem: Optional[plot_model.Item] = None
        self.__channel: Optional[scan_model.Channel] = None
        self.__treeView: Optional[qt.QTreeView] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

    def setEnvironment(
        self, treeView: qt.QTreeView, flintState: flint_model.FlintState
    ):
        self.__treeView = treeView
        self.__flintModel = flintState

    def setPlotModel(self, plotModel: plot_model.Plot):
        self.__plotModel = plotModel

    def items(self) -> List[qt.QStandardItem]:
        return [self, self.__used, self.__displayed, self.__style, self.__remove]

    def __usedChanged(self, item: qt.QStandardItem):
        if self.__plotItem is not None:
            # There is a plot item already
            assert self.__plotModel is not None
            self.__plotModel.removeItem(self.__plotItem)
        else:
            assert self.__channel is not None
            assert self.__plotModel is not None
            plot = self.__plotModel

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
        if device.isMaster():
            text = "Master %s" % device.name()
            icon = icons.getQIcon("flint:icons/item-timer")
        else:
            text = "Device %s" % device.name()
            icon = icons.getQIcon("flint:icons/item-device")
        self.setText(text)
        self.setIcon(icon)
        self.__used.setCheckable(False)

    def setChannel(self, channel: scan_model.Channel):
        self.__channel = channel
        text = "Channel %s" % channel.name()
        self.setText(text)
        icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)

        self.__used.modelUpdated = None
        self.__used.setCheckable(True)
        self.__used.modelUpdated = self.__usedChanged

    def setPlotItem(self, plotItem):
        self.__plotItem = plotItem

        self.__used.modelUpdated = None
        self.__used.setData(plotItem, role=delegates.PlotItemRole)
        self.__used.setCheckState(qt.Qt.Checked)
        self.__used.modelUpdated = self.__usedChanged

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

        if isinstance(plotItem, plot_item_model.ImageItem):
            icon = icons.getQIcon("flint:icons/item-channel")
            self.setIcon(icon)

        # FIXME: It have to be converted into delegate
        self.__treeView.openPersistentEditor(self.__displayed.index())
        self.__treeView.openPersistentEditor(self.__remove.index())
        widget = delegates.StylePropertyWidget(self.__treeView)
        widget.setPlotItem(self.__plotItem)
        widget.setFlintModel(self.__flintModel)
        self.__treeView.setIndexWidget(self.__style.index(), widget)


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

        self.__tree = qt.QTreeView(self)
        self.__tree.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__tree.setUniformRowHeights(True)

        self.__visibilityDelegate = delegates.VisibilityPropertyItemDelegate(self)
        self.__removeDelegate = delegates.RemovePropertyItemDelegate(self)

        model = qt.QStandardItemModel(self)
        self.__tree.setModel(model)

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

    def setFocusWidget(self, widget):
        if self.__focusWidget is not None:
            widget.plotModelUpdated.disconnect(self.__plotModelUpdated)
        self.__focusWidget = widget
        if self.__focusWidget is not None:
            widget.plotModelUpdated.connect(self.__plotModelUpdated)
        self.__plotModelUpdated(widget.plotModel())

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

    def __currentScanChanged(self):
        self.__setScan(self.__flintModel.currentScan())

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

    def __updateTree(self):
        # FIXME: expanded/collapsed items have to be restored

        model = self.__tree.model()
        model.clear()

        if self.__plotModel is None:
            foo = qt.QStandardItem("Empty")
            model.appendRow(foo)
            return

        model.setHorizontalHeaderLabels(
            ["Name", "Use", "Displayed", "Style", "Remove", ""]
        )
        self.__tree.setItemDelegateForColumn(
            self.VisibleColumn, self.__visibilityDelegate
        )
        self.__tree.setItemDelegateForColumn(self.RemoveColumn, self.__removeDelegate)
        header = self.__tree.header()
        header.setSectionResizeMode(self.NameColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.UseColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.VisibleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.StyleColumn, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.RemoveColumn, qt.QHeaderView.ResizeToContents)

        scanTree = {}
        channelItems = {}

        scan = self.__scan

        if scan is not None:
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
                parent.appendRow(item.items())
                # It have to be done when model index are initialized
                item.setDevice(device)

                for channel in device.channels():
                    if channel.type() != scan_model.ChannelType.IMAGE:
                        continue
                    channelItem = _DataItem()
                    channelItem.setEnvironment(self.__tree, self.__flintModel)
                    item.appendRow(channelItem.items())
                    # It have to be done when model index are initialized
                    channelItem.setChannel(channel)
                    channelItem.setPlotModel(self.__plotModel)
                    channelItems[channel.name()] = channelItem

        itemWithoutLocation = qt.QStandardItem("Not linked to this scan")
        model.appendRow(itemWithoutLocation)

        for plotItem in self.__plotModel.items():
            if not isinstance(plotItem, plot_item_model.ImageItem):
                continue

            dataChannel = plotItem.imageChannel()
            if dataChannel is None:
                continue

            dataChannelName = dataChannel.name()
            if dataChannelName in channelItems:
                channelItem = channelItems[dataChannelName]
                channelItem.setPlotItem(plotItem)
            else:
                itemClass = plotItem.__class__
                text = "%s" % itemClass.__name__
                item = _DataItem(text)
                item.setEnvironment(self.__tree, self.__flintModel)
                itemWithoutLocation.appendRow(item.items())
                # It have to be done when model index are initialized
                item.setPlotItem(plotItem)

        self.__tree.expandAll()
