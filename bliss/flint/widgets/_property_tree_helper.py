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
            text = "Master %s" % device.name()
            icon = icons.getQIcon("flint:icons/item-timer")
        else:
            text = "Device %s" % device.name()
            icon = icons.getQIcon("flint:icons/item-device")
        self.setText(text)
        self.setIcon(icon)

    def setChannelLookAndFeel(self, channel: scan_model.Channel):
        text = "Channel %s" % channel.name()
        self.setText(text)
        icon = icons.getQIcon("flint:icons/item-channel")
        self.setIcon(icon)

    def setPlotItemLookAndFeel(self, plotItem: plot_model.Item, updateText=False):
        if isinstance(plotItem, plot_curve_model.CurveItem):
            icon = icons.getQIcon("flint:icons/item-channel")
        elif isinstance(plotItem, plot_curve_model.CurveMixIn):
            icon = icons.getQIcon("flint:icons/item-func")
        elif isinstance(plotItem, plot_curve_model.CurveStatisticMixIn):
            icon = icons.getQIcon("flint:icons/item-stats")
        self.setIcon(icon)

        if updateText:
            itemClass = plotItem.__class__
            text = "%s" % itemClass.__name__
            self.setText(text)
