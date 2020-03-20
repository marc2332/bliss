# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import List

import logging

from silx.gui import qt
from bliss.flint.helper import scan_history


_logger = logging.getLogger(__name__)


class ScanHistoryDialog(qt.QDialog):

    NodeNameRole = qt.Qt.UserRole + 1

    def __init__(self, parent=None):
        super(ScanHistoryDialog, self).__init__(parent=parent)

        self.__table = qt.QTableView(self)
        self.__table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.__table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.__table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        model = qt.QStandardItemModel(self)
        self.__table.setModel(model)

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
        scans = scan_history.get_all_scans(sessionName)
        model = self.__table.model()
        model.clear()
        for scan in scans:
            titleItem = qt.QStandardItem()
            titleItem.setText(scan.title)
            titleItem.setData(scan.node_name, role=self.NodeNameRole)
            model.appendRow([titleItem])

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
