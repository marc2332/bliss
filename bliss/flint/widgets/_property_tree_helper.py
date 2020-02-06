# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Shared objects to create a property tree."""

from __future__ import annotations
from typing import List
from typing import Dict

from silx.gui import qt
from silx.gui import icons

from bliss.flint.model import scan_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_item_model
from bliss.flint.model import plot_state_model


class StandardRowItem(qt.QStandardItem):
    """Default standard item to simplify creation of trees with many columns.

    This item is tghe first item of the row (first column) and store other
    items of the row (other columns).

    The method `rowItems` provides the list of the item in the row, in order to
    append it to other items of the tree using the default `appendRow` method.

    .. code-block::

        parent.appendRow(item.rowItems())
    ```
    """

    def __init__(self):
        super(StandardRowItem, self).__init__()
        self.__rowItems = [self]

    def setOtherRowItems(self, *args):
        self.__rowItems = [self]
        self.__rowItems.extend(args)

    def rowItems(self) -> List[qt.QStandardItem]:
        return self.__rowItems


class ScanRowItem(StandardRowItem):
    """Helper to provide consistent look and feel for all the property trees."""

    def setDeviceLookAndFeel(self, device: scan_model.Device):
        if device.isMaster():
            text = device.name()
            icon = icons.getQIcon("flint:icons/device-timer")
            toolTip = "Master %s" % device.name()
        else:
            text = device.name()
            icon = icons.getQIcon("flint:icons/device-default")
            toolTip = "Device %s" % device.name()
        self.setText(text)
        self.setIcon(icon)
        self.setToolTip(toolTip)

    def setChannelLookAndFeel(self, channel: scan_model.Channel):
        text = channel.baseName()
        if channel.type() == scan_model.ChannelType.COUNTER:
            icon = icons.getQIcon("flint:icons/channel-curve")
        elif channel.type() == scan_model.ChannelType.SPECTRUM:
            icon = icons.getQIcon("flint:icons/channel-spectrum")
        elif channel.type() == scan_model.ChannelType.IMAGE:
            icon = icons.getQIcon("flint:icons/channel-image")
        else:
            icon = icons.getQIcon("flint:icons/channel-curve")

        toolTip = "Channel %s" % channel.name()
        self.setText(text)
        self.setIcon(icon)
        self.setToolTip(toolTip)

    def setPlotItemLookAndFeel(self, plotItem: plot_model.Item):
        if isinstance(plotItem, plot_item_model.CurveItem):
            icon = icons.getQIcon("flint:icons/channel-curve")
        elif isinstance(plotItem, plot_item_model.McaItem):
            icon = icons.getQIcon("flint:icons/channel-spectrum")
        elif isinstance(plotItem, plot_item_model.ImageItem):
            icon = icons.getQIcon("flint:icons/channel-image")
        elif isinstance(plotItem, plot_item_model.ScatterItem):
            icon = icons.getQIcon("flint:icons/channel-curve")
        elif isinstance(plotItem, plot_state_model.CurveStatisticItem):
            icon = icons.getQIcon("flint:icons/item-stats")
        elif isinstance(plotItem, plot_item_model.CurveMixIn):
            icon = icons.getQIcon("flint:icons/item-func")
        else:
            icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)

        itemClass = plotItem.__class__
        text = "%s" % itemClass.__name__
        self.setText(text)


def getPathFromCollapsedNodes(view: qt.QAbstractItemView) -> List[str]:
    """Return relative path from the root index of the extended nodes"""
    model = view.model()
    paths: List[str] = []
    indexes = [(None, qt.QModelIndex())]
    while len(indexes):
        path, index = indexes.pop(0)
        if path is not None:
            if not view.isExpanded(index):
                paths.append(path)

        for child in range(model.rowCount(index)):
            childIndex = model.index(child, 0, index)
            name = model.data(childIndex, role=qt.Qt.DisplayRole)
            if path is None:
                childPath = "/%s" % name
            else:
                childPath = "%s/%s" % (path, name)
            indexes.append((childPath, childIndex))
    return paths


def collapseNodesFromPaths(view: qt.QAbstractItemView, paths: List[str]):
    model = view.model()
    indexes = indexesFromPaths(model, paths)
    for index in indexes:
        view.setExpanded(index, False)


def indexesFromPaths(model: qt.QAbstractItemModel, paths: List[str]):
    cache: Dict[List[str], qt.QModelIndex] = {}
    indexes = []

    def getIndexFromName(
        model: qt.QAbstractItemModel, index: qt.QModelIndex, name: str
    ):
        for child in range(model.rowCount(index)):
            childIndex = model.index(child, 0, index)
            childName = model.data(childIndex)
            if childName == name:
                return childIndex
        return None

    for path in paths:
        if len(path) > 0 and path[0] == "/":
            path = path[1:]
        elements = tuple(path.split("/"))

        # Reach the first available parent
        parent = None
        i = 0
        for i in reversed(range(len(elements) - 1)):
            key = elements[:i]
            parent = cache.get(key, None)
            if parent is not None:
                break
        if parent is None:
            parent = qt.QModelIndex()

        # Reach the next elements
        for j in range(i, len(elements)):
            key = elements[0 : j + 1]
            index = getIndexFromName(model, parent, elements[j])
            if index is None:
                break
            cache[key] = index
            parent = index

        if index is not None:
            indexes.append(index)

    return indexes
