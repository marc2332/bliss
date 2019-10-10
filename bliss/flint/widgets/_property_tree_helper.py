# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Shared objects to create a property tree."""

from __future__ import annotations
from typing import List

from silx.gui import qt
from silx.gui import icons

from bliss.flint.model import scan_model
from bliss.flint.model import plot_model
from bliss.flint.model import plot_curve_model
from bliss.flint.model import plot_item_model


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
        if isinstance(plotItem, plot_curve_model.CurveItem):
            icon = icons.getQIcon("flint:icons/channel-curve")
        elif isinstance(plotItem, plot_item_model.McaItem):
            icon = icons.getQIcon("flint:icons/channel-spectrum")
        elif isinstance(plotItem, plot_item_model.ImageItem):
            icon = icons.getQIcon("flint:icons/channel-image")
        elif isinstance(plotItem, plot_item_model.ScatterItem):
            icon = icons.getQIcon("flint:icons/channel-curve")
        elif isinstance(plotItem, plot_curve_model.CurveMixIn):
            icon = icons.getQIcon("flint:icons/item-func")
        elif isinstance(plotItem, plot_curve_model.CurveStatisticMixIn):
            icon = icons.getQIcon("flint:icons/item-stats")
        else:
            icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)

        itemClass = plotItem.__class__
        text = "%s" % itemClass.__name__
        self.setText(text)
