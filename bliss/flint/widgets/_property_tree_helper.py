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
