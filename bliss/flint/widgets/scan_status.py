# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import List

import time
import logging

from silx.gui import qt
import silx.resources

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget
from bliss.flint.utils import stringutils
from bliss.flint.helper import scan_info_helper


class _SingleScanStatus(qt.QWidget):
    def __init__(self, parent=None):
        super(_SingleScanStatus, self).__init__(parent=parent)
        filename = silx.resources.resource_filename("flint:gui/scan-status.ui")

        # FIXME: remove this catch of warning when it is possible
        log = logging.getLogger("py.warnings")
        log.disabled = True
        widget = qt.loadUi(filename)
        log.disabled = False

        layout = qt.QVBoxLayout(self)
        layout.addWidget(widget)
        self.__widget = widget

        self.__scan: Optional[scan_model.Scan] = None
        self.__start: Optional(float) = None
        self.__end: Optional(float) = None
        self.__updateNoScan()

    def scan(self) -> Optional[scan_model.Scan]:
        return self.__scan

    def setScan(self, scan: scan_model.Scan = None):
        if self.__scan is scan:
            return
        if self.__scan is not None:
            self.__scan.scanStarted.disconnect(self.__scanStarted)
            self.__scan.scanFinished.disconnect(self.__scanFinished)
        self.__scan = scan
        if self.__scan is not None:
            self.__scan.scanStarted.connect(self.__scanStarted)
            self.__scan.scanFinished.connect(self.__scanFinished)
        self.__updateScan()

    def __updateScan(self):
        scan = self.__scan
        if scan is None:
            self.__updateNoScan()
        else:
            if scan.state() == scan_model.ScanState.PROCESSING:
                self.__widget.process.setVisible(True)
                self.__widget.noAcquisition.setVisible(False)
                self.__widget.noAcquisition.setText("PROCESSING")
                self.__updateScanInfo()
                self.updateRemaining()
            elif scan.state() == scan_model.ScanState.FINISHED:
                self.__widget.process.setVisible(False)
                self.__widget.noAcquisition.setVisible(True)
                self.__widget.noAcquisition.setText("FINISHED")
                self.__widget.remainingTime.setText("")
            elif scan.state() == scan_model.ScanState.INITIALIZED:
                self.__widget.process.setVisible(False)
                self.__widget.noAcquisition.setVisible(True)
                self.__widget.noAcquisition.setText("INITIALIZING")
                self.__widget.remainingTime.setText("")

    def __updateNoScan(self):
        self.__widget.scanInfo.setText("No scan available")
        self.__widget.process.setVisible(False)
        self.__widget.noAcquisition.setVisible(True)
        self.__widget.noAcquisition.setText("NO SCAN")
        self.__widget.remainingTime.setText("")

    def __updateScanInfo(self):
        scan = self.__scan
        assert scan is not None
        title = scan_info_helper.get_full_title(scan)
        self.__widget.scanInfo.setText(title)

        scan_info = scan.scanInfo()
        self.__end = None
        self.__widget.process.setEnabled(False)
        self.__widget.remainingTime.setText("No estimation time")

    def updateRemaining(self):
        scan = self.__scan
        if self.__end is not None:
            now = time.time()
            remaining = self.__end - now
            if remaining < 0:
                remaining = 0
            remaining = stringutils.human_readable_duration(seconds=round(remaining))
            self.__widget.remainingTime.setText(f"Remaining time: {remaining}")
        percent = scan_info_helper.get_scan_progress_percent(scan)
        if percent is not None:
            self.__widget.process.setValue(percent * 100)
            self.__widget.process.setEnabled(True)

    def __scanStarted(self):
        self.__start = time.time()
        self.__updateScan()

    def __scanFinished(self):
        self.__start = None
        self.__end = None
        self.__updateScan()


class ScanStatus(ExtendedDockWidget):
    def __init__(self, parent=None):
        super(ScanStatus, self).__init__(parent=parent)

        self.__widget = qt.QWidget(self)
        _ = qt.QVBoxLayout(self.__widget)

        self.__scanWidgets: List[_SingleScanStatus] = []

        # Try to improve the look and feel
        # FIXME: THis should be done with stylesheet
        frame = qt.QFrame(self)
        frame.setFrameShape(qt.QFrame.StyledPanel)
        layout = qt.QVBoxLayout(frame)
        layout.addWidget(self.__widget)
        layout.setContentsMargins(0, 0, 0, 0)
        widget = qt.QFrame(self)
        layout = qt.QVBoxLayout(widget)
        layout.addWidget(frame)
        layout.setContentsMargins(0, 1, 0, 0)
        self.setWidget(widget)

        widget.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred)

        self.__flintModel: Optional[flint_model.FlintState] = None

        self.__timer = qt.QTimer(self)
        self.__timer.setInterval(1000)
        self.__timer.timeout.connect(self.__updateWidgets)

        holder = _SingleScanStatus(self)
        self.__addScanWidget(holder)

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        if self.__flintModel is not None:
            self.__flintModel.aliveScanAdded.disconnect(self.__aliveScanAdded)
            self.__flintModel.aliveScanRemoved.disconnect(self.__aliveScanRemoved)
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.aliveScanAdded.connect(self.__aliveScanAdded)
            self.__flintModel.aliveScanRemoved.connect(self.__aliveScanRemoved)
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)

    def __addScanWidget(self, widget):
        layout = self.__widget.layout()

        # Clear dead widgets
        safeList = list(self.__scanWidgets)
        for otherWidget in safeList:
            scan = otherWidget.scan()
            if scan is None or scan.state() == scan_model.ScanState.FINISHED:
                self.__scanWidgets.remove(otherWidget)
                otherWidget.deleteLater()

        layout.addWidget(widget)
        self.__scanWidgets.append(widget)
        self.updateGeometry()

        scan = widget.scan()
        if scan is not None and scan.state() in [
            scan_model.ScanState.PROCESSING,
            scan_model.ScanState.INITIALIZED,
        ]:
            if not self.__timer.isActive():
                self.__timer.start()

    def __updateWidgets(self):
        for widget in self.__scanWidgets:
            widget.updateRemaining()

    def __removeWidgetFromScan(self, scan):
        if len(self.__scanWidgets) == 1:
            # Do not remove the last scan widget
            if self.__timer.isActive():
                self.__timer.stop()
            return

        if self.__flintModel.currentScan() is scan:
            # Do not remove the current scan widget
            # Right now it is the one displayed by the other widgets
            return

        widgets = [w for w in self.__scanWidgets if w.scan() is scan]
        if len(widgets) == 0:
            # No widget for this scan
            return

        assert len(widgets) == 1
        widget = widgets[0]

        self.__scanWidgets.remove(widget)
        widget.deleteLater()

    def __aliveScanAdded(self, scan):
        widget = _SingleScanStatus(self)
        widget.setScan(scan)
        self.__addScanWidget(widget)

    def __aliveScanRemoved(self, scan):
        self.__removeWidgetFromScan(scan)

    def __currentScanChanged(self):
        # TODO: The current scan could be highlighted
        pass
