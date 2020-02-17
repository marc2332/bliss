# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helper relative to Qt models"""

from silx.gui import qt


def iterAllItems(
    model: qt.QAbstractItemModel, parent: qt.QModelIndex = qt.QModelIndex()
):
    """Iterate through all the items contained in a tree

    The returned indices only contains index with column 0
    """
    for i in range(model.rowCount(parent)):
        index: qt.QModelIndex = model.index(i, 0, parent)
        yield index
        if model.hasChildren(index):
            for subIndex in iterAllItems(model, index):
                yield subIndex
