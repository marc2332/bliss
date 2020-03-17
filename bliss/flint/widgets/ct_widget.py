# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import Tuple
from typing import Dict
from typing import List
from typing import NamedTuple
import numbers

import logging

from silx.gui import qt
from silx.gui import icons

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.helper import scan_info_helper
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget


_logger = logging.getLogger(__name__)


class CtWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    scanModelUpdated = qt.Signal(object)
    """Emitted when the scan model displayed by the plot was changed"""

    def __init__(self, parent=None):
        super(CtWidget, self).__init__(parent=parent)

        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

        mainWidget = qt.QFrame(self)
        mainWidget.setFrameShape(qt.QFrame.StyledPanel)

        self.__table = qt.QTableView(mainWidget)
        model = qt.QStandardItemModel(self.__table)
        self.__table.setModel(model)
        self.__table.setFrameShape(qt.QFrame.NoFrame)

        self.__title = qt.QLabel(mainWidget)
        self.__title.setAlignment(qt.Qt.AlignHCenter)
        self.__title.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        self.__title.setStyleSheet("QLabel {font-size: 14px;}")

        layout = qt.QVBoxLayout(mainWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.__title)
        layout.addWidget(self.__table)

        # Try to improve the look and feel
        # FIXME: THis should be done with stylesheet
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(mainWidget)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

    def createPropertyWidget(self, parent: qt.QWidget):
        propertyWidget = qt.QWidget(parent)
        return propertyWidget

    def flintModel(self) -> Optional[flint_model.FlintState]:
        return self.__flintModel

    def setFlintModel(self, flintModel: Optional[flint_model.FlintState]):
        self.__flintModel = flintModel

    def scan(self) -> Optional[scan_model.Scan]:
        return self.__scan

    def setScan(self, scan: scan_model.Scan = None):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].disconnect(self.__scanDataUpdated)
            self.__scan.scanStarted.disconnect(self.__scanStarted)
            self.__scan.scanFinished.disconnect(self.__scanFinished)
        self.__scan = scan
        # As the scan was updated, clear the previous cached events
        if self.__scan is not None:
            self.__scan.scanDataUpdated[object].connect(self.__scanDataUpdated)
            self.__scan.scanStarted.connect(self.__scanStarted)
            self.__scan.scanFinished.connect(self.__scanFinished)
            if self.__scan.state() != scan_model.ScanState.INITIALIZED:
                self.__updateTitle(self.__scan)
        self.scanModelUpdated.emit(scan)

        self.__redrawAll()

    def __clear(self):
        model = self.__table.model()
        model.clear()

    def __scanStarted(self):
        self.__updateFields()
        self.__updateTitle()

    def __updateTitle(self):
        scan = self.__scan
        title = scan_info_helper.get_full_title(scan)
        self.__title.setText(title)

    def __scanFinished(self):
        self.__updateData()

    def __scanDataUpdated(self, event: scan_model.ScanDataUpdateEvent):
        pass

    def __redrawAll(self):
        displayValue = self.__scan.state() != scan_model.ScanState.FINISHED
        self.__updateFields()
        if displayValue:
            self.__updateData()

    def __updateFields(self):
        model = self.__table.model()
        model.clear()
        model.setHorizontalHeaderLabels(["Channel", "Name", "Value", "Unit"])

        header = self.__table.verticalHeader()
        header.setVisible(False)

        header = self.__table.horizontalHeader()
        header.setSectionResizeMode(0, qt.QHeaderView.Fixed)
        header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, qt.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        header.setSectionHidden(0, True)

        scan = self.__scan
        if scan is None:
            return

        for device in scan.devices():
            for channel in device.channels():
                if channel.type() != scan_model.ChannelType.COUNTER:
                    continue

                channelName = channel.name()
                name = channel.displayName()
                unit = channel.unit()
                if unit is None:
                    unit = ""
                value = "..."

                data = [channelName, name, value, unit]
                items = [qt.QStandardItem(d) for d in data]
                model.appendRow(items)

    def __updateData(self):
        def reachValueFromChannel(channel: scan_model.Channel):
            data = channel.data()
            if data is None:
                return None
            array = data.array()
            if array is None:
                return None
            if len(array) <= 0:
                return None
            if len(array) >= 2:
                raise RuntimeError("More than one value returned")
            return array[0]

        scan = self.__scan
        if scan is None:
            return

        integrationTime = scan.scanInfo()["count_time"]
        model = self.__table.model()

        for i in range(model.rowCount()):
            channelItem = model.item(i, 0)
            nameItem = model.item(i, 1)
            valueItem = model.item(i, 2)
            unitItem = model.item(i, 3)
            channel = scan.getChannelByName(channelItem.text())

            try:
                value = reachValueFromChannel(channel)
                value = str(value)
                icon = qt.QIcon()
            except Exception as e:
                value = e.args[0]
                icon = icons.getQIcon("flint:icons/warning")

            valueItem.setText(value)
            valueItem.setIcon(icon)
