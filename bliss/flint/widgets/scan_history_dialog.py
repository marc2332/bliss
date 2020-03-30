# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import List

import logging
import datetime

from silx.gui import qt
from silx.gui import icons
from bliss.flint.helper import scan_history


_logger = logging.getLogger(__name__)


class _IdDelegate(qt.QStyledItemDelegate):
    def initStyleOption(self, option: qt.QStyleOptionViewItem, index: qt.QModelIndex):
        super(_IdDelegate, self).initStyleOption(option, index)

        scanType = index.data(ScanHistoryDialog.ScanTypeRole)
        if scanType is not None:
            if scanType in ["ct", "runct"]:
                icon = icons.getQIcon("flint:icons/scantype-point")
            elif scanType in [
                "dscan",
                "ascan",
                "d2scan",
                "a2scan",
                "d3scan",
                "a3scan",
                "d4scan",
                "a4scan",
                "dnscan",
                "anscan",
            ]:
                icon = icons.getQIcon("flint:icons/scantype-nscan")
            elif scanType in ["amesh", "dmesh"]:
                icon = icons.getQIcon("flint:icons/scantype-mesh")
            else:
                icon = qt.QIcon()
        else:
            icon = qt.QIcon()

        option.features = (
            option.features | qt.QStyleOptionViewItem.ViewItemFeature.HasDecoration
        )
        option.icon = icon

    def displayText(self, value, locale: qt.QLocale):
        if isinstance(value, int):
            return "#%d" % value
        return qt.QStyledItemDelegate.displayText(self, value, locale)


class _DateDelegate(qt.QStyledItemDelegate):
    def displayText(self, value, locale: qt.QLocale):
        if not isinstance(value, datetime.datetime):
            return qt.QStyledItemDelegate.displayText(self, value, locale)

        now = datetime.datetime.now()
        if now.isocalendar() == value.isocalendar():
            return "Today"
        today = datetime.datetime(now.year, now.month, now.day)
        if (today - value) <= datetime.timedelta(days=1):
            return "Yesterday"

        return value.strftime("%Y-%m-%d")


class _TimeDelegate(qt.QStyledItemDelegate):
    def displayText(self, value, locale: qt.QLocale):
        if not isinstance(value, datetime.datetime):
            return qt.QStyledItemDelegate.displayText(self, value, locale)
        return value.strftime("%H:%M")


class ScanHistoryDialog(qt.QDialog):

    NodeNameRole = qt.Qt.UserRole + 1
    ScanTypeRole = qt.Qt.UserRole + 2

    def __init__(self, parent=None):
        super(ScanHistoryDialog, self).__init__(parent=parent)

        self.setWindowTitle("Scan selection")
        self.__table = qt.QTableView(self)
        self.__table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.__table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.__table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        model = qt.QStandardItemModel(self)
        self.__table.setModel(model)
        model = self.__table.model()

        self.__buttons = qt.QDialogButtonBox(self)
        self.__buttons.accepted.connect(self.accept)
        self.__buttons.rejected.connect(self.reject)
        self.__select = self.__buttons.addButton(qt.QDialogButtonBox.Open)
        self.__cancel = self.__buttons.addButton(qt.QDialogButtonBox.Cancel)

        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.__table)
        layout.addWidget(self.__buttons)

    def setSessionName(self, sessionName: str):
        # FIXME: it should be done in a greenlet
        self.__loadScans(sessionName)

    def __loadScans(self, sessionName: str):
        model = self.__table.model()
        model.clear()
        model.setHorizontalHeaderLabels(["ID", "Date", "Time", "Command"])

        header = self.__table.verticalHeader()
        header.setVisible(False)

        delegate = _IdDelegate(self.__table)
        self.__table.setItemDelegateForColumn(0, delegate)
        delegate = _DateDelegate(self.__table)
        self.__table.setItemDelegateForColumn(1, delegate)
        delegate = _TimeDelegate(self.__table)
        self.__table.setItemDelegateForColumn(2, delegate)

        header = self.__table.horizontalHeader()
        header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, qt.QHeaderView.Stretch)
        header.setStretchLastSection(True)

        scans = scan_history.get_all_scans(sessionName)
        for scan in scans:
            if scan.title is not None:
                scanType = scan.title.split(" ")[0]
            else:
                scanType = ""

            idItem = qt.QStandardItem()
            idItem.setData(scan.scan_nb, role=qt.Qt.DisplayRole)
            idItem.setData(scan.node_name, role=self.NodeNameRole)
            idItem.setData(scanType, self.ScanTypeRole)

            dateItem = qt.QStandardItem()
            dateItem.setData(scan.start_time, role=qt.Qt.DisplayRole)
            timeItem = qt.QStandardItem()
            timeItem.setData(scan.start_time, role=qt.Qt.DisplayRole)

            commandItem = qt.QStandardItem()
            commandItem.setText(scan.title)
            commandItem.setData(scan.node_name, role=self.NodeNameRole)

            model.appendRow([idItem, dateItem, timeItem, commandItem])

        # Select the last scan
        lastRow = model.rowCount() - 1
        self.__table.selectRow(lastRow)

    def selectedScanNodeNames(self) -> List[str]:
        selection = self.__table.selectedIndexes()
        result = []
        for s in selection:
            if not s.isValid():
                continue
            if s.column() != 0:
                continue
            result.append(s.data(role=self.NodeNameRole))
        return result
