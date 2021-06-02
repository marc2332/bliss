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


class ProxyColumnModel(qt.QIdentityProxyModel):
    """Provides proxyfied multi columns pointing to the same source column.
    """

    def __init__(self, parent=None):
        qt.QIdentityProxyModel.__init__(self, parent=parent)
        self.__columns = 0
        self.__columnTitle = {}
        self.__columnEditor = set()

    def setColumn(self, columnId: int, title: str):
        """Define a column to this model.

        This new column will point to the first column of the source model.
        """
        self.beginResetModel()
        self.__columns = max(self.__columns, columnId + 1)
        self.__columnTitle[columnId] = title
        self.endResetModel()

    def setColumnEditor(self, columnId: int, editor: bool):
        if editor:
            self.__columnEditor.add(columnId)
        else:
            self.__columnEditor.discard(columnId)

    def data(self, index: qt.QModelIndex, role: int = qt.Qt.DisplayRole):
        if index.isValid():
            if role == qt.Qt.DisplayRole:
                if index.column() in self.__columnEditor:
                    return ""
        return qt.QIdentityProxyModel.data(self, index, role)

    def object(self, index: qt.QModelIndex):
        return self.data(index, role=delegates.ObjectRole)

    def columnCount(self, parent: qt.QModelIndex = qt.QModelIndex()):
        return self.__columns

    def rowCount(self, parent: qt.QModelIndex = qt.QModelIndex()):
        sourceModel = self.sourceModel()
        if sourceModel is None:
            return 0
        parent = self.mapToSource(parent)
        result = sourceModel.rowCount(parent)
        return result

    def index(self, row, column, parent=qt.QModelIndex()):
        if column != 0:
            firstCol = self.index(row, 0, parent)
            return self.createIndex(row, column, firstCol.internalPointer())
        return super(ProxyColumnModel, self).index(row, column, parent)

    def parent(self, child):
        if not child.isValid():
            return qt.QModelIndex()
        if child.column() != 0:
            child = self.createIndex(child.row(), 0, child.internalPointer())
        return super(ProxyColumnModel, self).parent(child)

    def mapFromSource(self, sourceIndex: qt.QModelIndex) -> qt.QModelIndex:
        if not sourceIndex.isValid():
            return qt.QModelIndex()
        if sourceIndex.column() != 0:
            return qt.QModelIndex()
        return super(ProxyColumnModel, self).mapFromSource(sourceIndex)

    def mapToSource(self, proxyIndex: qt.QModelIndex) -> qt.QModelIndex:
        if not proxyIndex.isValid():
            return qt.QModelIndex()
        if proxyIndex.column() != 0:
            proxyIndex = self.createIndex(
                proxyIndex.row(), 0, proxyIndex.internalPointer()
            )
        return super(ProxyColumnModel, self).mapToSource(proxyIndex)

    def headerData(
        self,
        section: int,
        orientation: qt.Qt.Orientation,
        role: int = qt.Qt.DisplayRole,
    ):
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                return self.__columnTitle.get(section, str(section))
        sourceModel = self.sourceModel()
        if sourceModel is None:
            return None
        if orientation == qt.Qt.Horizontal:
            return sourceModel.headerData(0, orientation, role)
        return sourceModel.headerData(section, orientation, role)


class ObjectListModel(qt.QAbstractItemModel):
    """Store a list of object as a Qt model.

    For now, it only supports to set the whole list. No move or remove
    actions are supported.
    """

    def __init__(self, parent=None):
        super(ObjectListModel, self).__init__(parent=parent)
        self.__items: typing.List[object] = []

    def setObjectList(self, items: typing.List[object]):
        self.beginResetModel()
        self.__items = list(items)
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

    def data(self, index: qt.QModelIndex, role: int = qt.Qt.DisplayRole):
        row = index.row()
        item = self.__items[row]
        if role == delegates.ObjectRole:
            return item
        elif role == qt.Qt.DisplayRole:
            return str(item)
        return None

    def columnCount(self, parent: qt.QModelIndex = qt.QModelIndex()):
        return 1


class VDataTableView(qt.QTableView):
    """
    Table view using a source model with a single column. A proxy column can
    be defined and have to be delegate to display expected content.

    The default behaviour is to display columns as item delegate.
    Therefor, the method `setColumn` is used to define the layout of the table.

    The view is based on a specific proxy model, thisfor the `setSourceModel`
    have to be used instead of `setModel`.
    """

    def __init__(self, parent=None):
        super(VDataTableView, self).__init__(parent=parent)
        self.__columnsDelegated = set()
        self.__proxyModel = ProxyColumnModel(self)
        self.__proxyModel.modelReset.connect(self.__modelWasReset)
        super(VDataTableView, self).setModel(self.__proxyModel)
        self.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        header = self.horizontalHeader()
        header.setHighlightSections(False)

    def reset(self):
        qt.QTableView.reset(self)
        self.__modelWasReset()

    def showEvent(self, event):
        qt.QTableView.showEvent(self, event)
        # Editors have to be open  when the widget is shown
        self.__modelWasReset()

    def indexToView(self, index, column=None):
        """Make sure an index can be used by the view."""
        if index.model() is self.__proxyModel.sourceModel():
            index = self.__proxyModel.mapFromSource(index)
            if column is not None:
                parent = index.parent()
                index = self.__proxyModel.index(index.row(), column, parent)
        return index

    def indexWidget(self, index, column=None):
        index = self.indexToView(index, column=column)
        return super(VDataTableView, self).indexWidget(index)

    def __modelWasReset(self):
        """
        Enforce that each editors are open.
        """
        if self.isHidden():
            return
        model = self.model()
        for c in self.__columnsDelegated:
            for r in range(model.rowCount()):
                index = model.index(r, c)
                self.openPersistentEditor(index)

    def setModel(self, model):
        raise RuntimeError("Model is reserved. Use setSourceModel instead")

    def setSourceModel(self, model):
        """Set the model used by this view.

        As this model enforce a specific proxy model, this method provides a
        direct access to the model set by the business logic."""
        self.__proxyModel.setSourceModel(model)

    def sourceModel(self):
        """Source model used by the proxy model enforced by this view"""
        return self.__proxyModel.sourceModel()

    def setColumn(
        self,
        logicalColumnId: int,
        title: str,
        delegate: typing.Union[
            typing.Type[qt.QAbstractItemDelegate], qt.QAbstractItemDelegate
        ] = None,
        resizeMode: qt.QHeaderView.ResizeMode = None,
    ):
        """
        Define a column.

        Arguments:
            logicalColumnId: Logical column id
            title: Title of this column
            delegate: An item delegate instance or class
            resizeMode: Mode used to resize the column
        """
        self.__proxyModel.setColumn(logicalColumnId, title)
        if resizeMode is not None:
            header = self.horizontalHeader()
            header.setSectionResizeMode(logicalColumnId, resizeMode)
        if delegate is not None:
            if issubclass(delegate, qt.QAbstractItemDelegate):
                delegate = delegate(self)
            if hasattr(delegate, "EDITOR_ALWAYS_OPEN"):
                if delegate.EDITOR_ALWAYS_OPEN:
                    self.__columnsDelegated.add(logicalColumnId)
                    self.__proxyModel.setColumnEditor(logicalColumnId, True)
            self.setItemDelegateForColumn(logicalColumnId, delegate)

    def setDisplayedColumns(self, logicalColumnIds: typing.List[int]):
        """
        Defines order and visibility of columns by logical indexes.

        Arguments:
            logicalColumnIds: List of logical column indexes to display
        """
        header = self.horizontalHeader()
        for pos, columnId in enumerate(logicalColumnIds):
            currentPos = header.visualIndex(columnId)
            header.moveSection(currentPos, pos)
            header.setSectionHidden(columnId, False)
        for columnId in set(range(header.model().columnCount())) - set(
            logicalColumnIds
        ):
            header.setSectionHidden(columnId, True)
