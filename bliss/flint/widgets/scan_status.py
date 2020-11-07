# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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


_logger = logging.getLogger(__name__)


class _SingleScanStatus(qt.QWidget):
    def __init__(self, parent=None):
        super(_SingleScanStatus, self).__init__(parent=parent)
        filename = silx.resources.resource_filename("flint:gui/scan-status.ui")
        widget = qt.loadUi(filename)

        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        self.__widget = widget
        self.__widget.childProcess.setVisible(False)

        self.__scan: Optional[scan_model.Scan] = None
        self.__start: Optional(float) = None
        self.__end: Optional(float) = None

        self.__childScan: Optional[scan_model.Scan] = None
        self.__childStart: Optional(float) = None
        self.__childEnd: Optional(float) = None

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
                self.__widget.childProcess.setVisible(False)
                self.setActiveChildScan(None)
            elif scan.state() == scan_model.ScanState.INITIALIZED:
                self.__widget.process.setVisible(False)
                self.__widget.noAcquisition.setVisible(True)
                self.__widget.noAcquisition.setText("INITIALIZING")

    def __updateNoScan(self):
        self.__widget.scanTitle.setText("No scan available")
        self.__widget.process.setVisible(False)
        self.__widget.noAcquisition.setVisible(True)
        self.__widget.noAcquisition.setText("NO SCAN")

    def __updateScanInfo(self):
        scan = self.__scan
        childScan = self.__childScan
        assert scan is not None
        title = scan_info_helper.get_full_title(scan)

        if childScan is not None:
            childTitle = scan_info_helper.get_full_title(childScan)
            title = f"{title} - {childTitle}"
        self.__widget.setToolTip(title)

        self.__childEnd = None
        self.__widget.childProcess.setEnabled(False)

        self.__widget.scanTitle.setText(title)

        self.__end = None
        self.__widget.process.setEnabled(False)

    def updateRemaining(self):
        scan = self.__scan
        if self.__end is not None:
            now = time.time()
            remaining = self.__end - now
            if remaining < 0:
                remaining = 0
            remaining = stringutils.human_readable_duration(seconds=round(remaining))
            # self.__widget.remainingTime.setText(f"Remaining time: {remaining}")
        percent = scan_info_helper.get_scan_progress_percent(scan)
        if percent is not None:
            self.__widget.process.setValue(percent * 100)
            self.__widget.process.setEnabled(True)

        self.updateChildRemaining()

    def __scanStarted(self):
        self.__start = time.time()
        self.__updateScan()

    def __scanFinished(self):
        self.__start = None
        self.__end = None
        self.__updateScan()

    def activeChildScan(self) -> Optional[scan_model.Scan]:
        return self.__childScan

    def setActiveChildScan(self, scan: scan_model.Scan = None):
        if self.__childScan is scan:
            return
        if self.__childScan is not None:
            self.__childScan.scanStarted.disconnect(self.__childScanStarted)
            self.__childScan.scanFinished.disconnect(self.__childScanFinished)
        self.__childScan = scan
        if self.__childScan is not None:
            self.__childScan.scanStarted.connect(self.__childScanStarted)
            self.__childScan.scanFinished.connect(self.__childScanFinished)
        self.__updateChildScan()

    def __updateChildScan(self):
        scan = self.__childScan
        if scan is None:
            self.__updateNoChildScan()
        else:
            if scan.state() == scan_model.ScanState.PROCESSING:
                self.__widget.childProcess.setVisible(True)
                self.updateChildRemaining()
            elif scan.state() == scan_model.ScanState.FINISHED:
                pass
            elif scan.state() == scan_model.ScanState.INITIALIZED:
                self.__widget.childProcess.setVisible(False)
        self.__updateScanInfo()

    def __updateNoChildScan(self):
        self.__widget.childProcess.setVisible(False)

    def updateChildRemaining(self):
        scan = self.__childScan
        if scan is None:
            return
        percent = scan_info_helper.get_scan_progress_percent(scan)
        if percent is not None:
            self.__widget.childProcess.setValue(percent * 100)
            self.__widget.childProcess.setEnabled(True)

    def __childScanStarted(self):
        self.__childStart = time.time()
        self.__updateChildScan()

    def __childScanFinished(self):
        self.__childStart = None
        self.__childEnd = None
        self.__updateChildScan()


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

    def __getWidgetByScan(self, scan):
        for w in self.__scanWidgets:
            if w.scan() is scan:
                return w
        return None

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
            if self.__scanWidgets[0].scan() is scan:
                _logger.debug("Update stopped")
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
        if scan.group() is not None:
            widget = self.__getWidgetByScan(scan.group())
            if widget is not None:
                widget.setActiveChildScan(scan)
                return

        widget = _SingleScanStatus(self)
        widget.setScan(scan)
        self.__addScanWidget(widget)

    def __aliveScanRemoved(self, scan):
        self.__removeWidgetFromScan(scan)

    def __currentScanChanged(self):
        # TODO: The current scan could be highlighted
        pass
