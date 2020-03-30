# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
import numbers

import logging

from silx.gui import qt

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.helper import scan_info_helper
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget


_logger = logging.getLogger(__name__)


class CenteringFloatingPointDot(qt.QStyledItemDelegate):
    def displayedRole(self) -> int:
        return qt.Qt.DisplayRole

    def displayText(self, value, locale):
        if isinstance(value, numbers.Number):
            return str(value)
        return str(value)

    def paint(
        self,
        painter: qt.QPainter,
        option: qt.QStyleOptionViewItem,
        index: qt.QModelIndex,
    ):
        value = index.data(self.displayedRole())
        if not isinstance(value, numbers.Number):
            return super(CenteringFloatingPointDot, self).paint(painter, option, index)

        text = option.text
        if text is None or text == "":
            text = self.displayText(value, option.locale)
            option.text = text
        if "." not in text:
            return super(CenteringFloatingPointDot, self).paint(painter, option, index)

        elements = text.split(".")
        fontMetrics = option.fontMetrics
        prefix = fontMetrics.width(elements[0])
        option.text = text
        width = option.rect.width()
        padding = width // 2 - prefix
        if padding > 0 and padding < width:
            option.rect.setLeft(option.rect.left() + padding)
        return super(CenteringFloatingPointDot, self).paint(painter, option, index)

    def sizeHint(self, option: qt.QStyleOptionViewItem, index: qt.QModelIndex):
        value = index.data(qt.Qt.SizeHintRole)
        if value is not None:
            return value
        value = index.data(self.displayedRole())
        if not isinstance(value, numbers.Number):
            return super(CenteringFloatingPointDot, self).sizeHint(option, index)

        text = option.text
        if text is None or text == "":
            text = self.displayText(value, option.locale)
            option.text = text
        if "." not in text:
            return super(CenteringFloatingPointDot, self).sizeHint(option, index)

        elements = text.split(".")
        fontMetrics = option.fontMetrics
        prefix = fontMetrics.width(elements[0])
        dot = fontMetrics.width(".")
        suffix = fontMetrics.width(elements[1])

        option.text = ""
        base = super(CenteringFloatingPointDot, self).sizeHint(option, index)
        option.text = text

        half = max(prefix, suffix)
        size = qt.QSize(half * 2 + dot + base.width(), base.height())
        return size


class MotorPositionDelegate(CenteringFloatingPointDot):
    def __init__(self, parent=None):
        super(MotorPositionDelegate, self).__init__(parent=parent)
        self.__displayDial = False

    def setDisplayDial(self, displayDial: bool):
        self.__displayDial = displayDial

    def displayedRole(self) -> int:
        if self.__displayDial:
            return PositionersWidget.DialPositionRole
        else:
            return PositionersWidget.UserPositionRole

    def initStyleOption(self, option: qt.QStyleOptionViewItem, index: qt.QModelIndex):
        super(MotorPositionDelegate, self).initStyleOption(option, index)

        value = index.data(self.displayedRole())
        if value is not None:
            option.features = (
                option.features | qt.QStyleOptionViewItem.ViewItemFeature.HasDisplay
            )
            option.text = self.displayText(value, option.locale)


class PositionersWidget(ExtendedDockWidget):

    widgetActivated = qt.Signal(object)

    scanModelUpdated = qt.Signal(object)
    """Emitted when the scan model displayed by the plot was changed"""

    UserPositionRole = qt.Qt.UserRole + 1
    DialPositionRole = qt.Qt.UserRole + 2

    def __init__(self, parent=None):
        super(PositionersWidget, self).__init__(parent=parent)

        self.__scan: Optional[scan_model.Scan] = None
        self.__flintModel: Optional[flint_model.FlintState] = None

        mainWidget = qt.QFrame(self)
        mainWidget.setFrameShape(qt.QFrame.StyledPanel)
        mainWidget.setAutoFillBackground(True)

        self.__table = qt.QTableView(mainWidget)
        model = qt.QStandardItemModel(self.__table)
        self.__table.setModel(model)
        self.__table.setFrameShape(qt.QFrame.NoFrame)
        self.__table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.__motorDelegate = MotorPositionDelegate(self.__table)

        self.__title = qt.QLabel(mainWidget)
        self.__title.setAlignment(qt.Qt.AlignHCenter)
        self.__title.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        self.__title.setStyleSheet("QLabel {font-size: 14px;}")

        toolbar = self.__createToolBar()

        line = qt.QFrame(self)
        line.setFrameShape(qt.QFrame.HLine)
        line.setFrameShadow(qt.QFrame.Sunken)

        layout = qt.QVBoxLayout(mainWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addWidget(line)
        layout.addWidget(self.__title)
        layout.addWidget(self.__table)

        # Try to improve the look and feel
        # FIXME: THis should be done with stylesheet
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(mainWidget)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

    def __createToolBar(self):
        toolBar = qt.QToolBar(self)
        toolBar.setMovable(False)

        self.__mode = qt.QActionGroup(self)
        self.__mode.setExclusive(True)
        self.__mode.triggered.connect(self.__displayModeChanged)

        self.__userPos = qt.QAction()
        self.__userPos.setText("User")
        self.__userPos.setToolTip("Display user motor position")
        self.__userPos.setCheckable(True)
        self.__userPos.setChecked(True)

        self.__dialPos = qt.QAction()
        self.__dialPos.setText("Dial")
        self.__dialPos.setToolTip("Display dial motor position")
        self.__dialPos.setCheckable(True)

        toolBar.addAction(self.__userPos)
        toolBar.addAction(self.__dialPos)
        self.__mode.addAction(self.__userPos)
        self.__mode.addAction(self.__dialPos)

        return toolBar

    def __displayModeChanged(self, action):
        if action is self.__userPos:
            self.__motorDelegate.setDisplayDial(False)
        elif action is self.__dialPos:
            self.__motorDelegate.setDisplayDial(True)
        else:
            assert False
        # NOTE: update is not working, i don't know why
        table = self.__table
        rect = table.rect()
        topLeft = table.indexAt(rect.topLeft())
        bottomRight = table.indexAt(rect.bottomRight())
        self.__table.dataChanged(topLeft, bottomRight)

    def createPropertyWidget(self, parent: qt.QWidget):
        propertyWidget = qt.QWidget(parent)
        return propertyWidget

    def flintModel(self) -> Optional[flint_model.FlintState]:
        return self.__flintModel

    def setFlintModel(self, flintModel: Optional[flint_model.FlintState]):
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)

    def __currentScanChanged(self):
        scan = self.__flintModel.currentScan()
        self.setScan(scan)

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
        displayResult = self.__scan.state() == scan_model.ScanState.FINISHED
        self.__updateFields()
        if displayResult:
            self.__updateData()

    def __updateFields(self):
        model = self.__table.model()
        model.clear()
        model.setHorizontalHeaderLabels(["Positioner", "Start", "End", "Unit"])

        header = self.__table.verticalHeader()
        header.setVisible(False)

        header = self.__table.horizontalHeader()
        header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(2, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(3, qt.QHeaderView.ResizeToContents)

        self.__table.setItemDelegateForColumn(1, self.__motorDelegate)
        self.__table.setItemDelegateForColumn(2, self.__motorDelegate)

        scan = self.__scan
        if scan is None:
            return

        scanInfo = scan.scanInfo()
        positioners = scan_info_helper.get_all_positioners(scanInfo)

        for positioner in positioners:
            positionerItem = qt.QStandardItem()
            positionerItem.setText(positioner.name)
            startItem = qt.QStandardItem()
            endItem = qt.QStandardItem()
            unitsItem = qt.QStandardItem()
            unitsItem.setText(positioner.units)

            startItem.setData(positioner.start, role=self.UserPositionRole)
            startItem.setData(positioner.dial_start, role=self.DialPositionRole)
            endItem.setData("...", role=self.UserPositionRole)
            endItem.setData("...", role=self.DialPositionRole)

            items = [positionerItem, startItem, endItem, unitsItem]
            model.appendRow(items)

    def __updateData(self):
        scan = self.__scan
        if scan is None:
            return

        scanInfo = scan.finalScanInfo()
        if scanInfo is None:
            return

        positioners = scan_info_helper.get_all_positioners(scanInfo)
        positioners = {p.name: p for p in positioners}

        model = self.__table.model()

        for i in range(model.rowCount()):
            positionerItem = model.item(i, 0)
            startItem = model.item(i, 1)
            endItem = model.item(i, 2)

            positionerName = positionerItem.text()
            positioner = positioners.get(positionerName, None)
            if positioner is None:
                #  Not anymore found
                # FIXME: The row should be removed
                continue

            startItem.setData(positioner.start, role=self.UserPositionRole)
            startItem.setData(positioner.dial_start, role=self.DialPositionRole)
            endItem.setData(positioner.end, role=self.UserPositionRole)
            endItem.setData(positioner.dial_end, role=self.DialPositionRole)
