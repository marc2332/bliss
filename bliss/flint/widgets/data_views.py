# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import typing
from silx.gui import qt
from . import delegates


_logger = logging.getLogger(__name__)


class ObjectListModel(qt.QAbstractItemModel):
    """Store a list of object as a Qt model.

    For now, it only supports to set the whole list. No move or remove
    actions are supported.
    """

    def __init__(self, parent=None):
        super(ObjectListModel, self).__init__(parent=parent)
        self.__items: typing.List[object] = []
        self.__delegatedColumns = set()
        self.__columns = 1
        self.__columnTitle = {}

    def setObjectList(self, items: typing.List[object]):
        self.beginResetModel()
        self.__items = list(items)
        self.endResetModel()

    def setColumn(self, columnId: int, title: str, delegated=False):
        self.beginResetModel()
        if delegated:
            self.__delegatedColumns.add(columnId)
        self.__columns = max(self.__columns, columnId + 1)
        self.__columnTitle[columnId] = title
        self.endResetModel()

    def rowCount(self, parent: qt.QModelIndex = qt.QModelIndex()):
        return len(self.__items)

    def index(self, row, column, parent=qt.QModelIndex()):
        if 0 <= row < len(self.__items):
            return self.createIndex(row, column)
        else:
            return qt.QModelIndex()

    def objectIndex(self, obj):
        try:
            row = self.__items.index(obj)
            return self.index(row, 0)
        except IndexError:
            return qt.QModelIndex()

    def object(self, index: qt.QModelIndex):
        return self.data(index, role=delegates.ObjectRole)

    def parent(self, index: qt.QModelIndex):
        return qt.QModelIndex()

    def flags(self, index: qt.QModelIndex):
        defaultFlags = qt.QAbstractItemModel.flags(self, index)
        if index.isValid():
            if index.column() in self.__delegatedColumns:
                return qt.Qt.ItemIsEditable | defaultFlags
        return defaultFlags

    def data(self, index: qt.QModelIndex, role: int = qt.Qt.DisplayRole):
        row = index.row()
        col = index.column()
        item = self.__items[row]
        if role == qt.Qt.DisplayRole:
            # Basic rendering
            if col in self.__delegatedColumns:
                return None
            return f"{str(item)}"
        elif role == delegates.ObjectRole:
            return item

    def headerData(
        self,
        section: int,
        orientation: qt.Qt.Orientation,
        role: int = qt.Qt.DisplayRole,
    ):
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                return self.__columnTitle.get(section, str(section))
        return super(ObjectListModel, self).headerData(section, orientation, role)

    def columnCount(self, parent: qt.QModelIndex = qt.QModelIndex()):
        return self.__columns


class VDataTableView(qt.QTableView):
    """
    Table view containing a single object per row which is displayed
    using many columns.

    The default behaviour is to display columns as item delegate.
    Therefor, the method `setColumn` is used to define the layout of the table.
    """

    def __init__(self, parent=None):
        super(VDataTableView, self).__init__(parent=parent)
        self.__columnsDelegated = set()
        self.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        header = self.horizontalHeader()
        header.setHighlightSections(False)

    def setModel(self, model: qt.QAbstractItemModel):
        if model is not None and not isinstance(model, ObjectListModel):
            raise ValueError(f"Unsupported model {type(model)}")
        previousModel = self.model()
        if previousModel is not None:
            previousModel.modelReset.disconnect(self.__modelWasReset)
        qt.QTableView.setModel(self, model)
        if model is not None:
            model.modelReset.connect(self.__modelWasReset)
        self.__modelWasReset()

    def __modelWasReset(self):
        """
        Enforce that each editors are open.
        """
        model = self.model()
        for c in self.__columnsDelegated:
            for r in range(model.rowCount()):
                index = model.index(r, c)
                self.openPersistentEditor(index)

    def setColumn(
        self,
        columnId: int,
        title: str,
        delegate: typing.Union[
            typing.Type[qt.QAbstractItemDelegate], qt.QAbstractItemDelegate
        ] = None,
        resizeMode: qt.QHeaderView.ResizeMode = None,
    ):
        """
        Define a column.

        Arguments:
            columnId: Logical column id
            title: Title of this column
            delegate: An item delegate instance or class
            resizeMode: Mode used to resize the column
        """
        model = self.model()
        model.setColumn(columnId, title=title, delegated=delegate is not None)
        if resizeMode is not None:
            header = self.horizontalHeader()
            header.setSectionResizeMode(columnId, resizeMode)
        if delegate is not None:
            if issubclass(delegate, qt.QAbstractItemDelegate):
                delegate = delegate(self)
            self.__columnsDelegated.add(columnId)
            self.setItemDelegateForColumn(columnId, delegate)
