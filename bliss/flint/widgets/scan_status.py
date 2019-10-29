# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional

import time
import logging

from silx.gui import qt
import silx.resources

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.widgets.extended_dock_widget import ExtendedDockWidget
from bliss.flint.utils import stringutils
from bliss.flint.helper import scan_info_helper


class ScanStatus(ExtendedDockWidget):
    def __init__(self, parent=None):
        super(ScanStatus, self).__init__(parent=parent)

        filename = silx.resources.resource_filename("flint:gui/scan-status.ui")

        # FIXME: remove this catch of warning when it is possible
        log = logging.getLogger("py.warnings")
        log.disabled = True
        widget = qt.loadUi(filename)
        log.disabled = False

        self.__widget = widget
        self.setWidget(self.__widget)
        self.__widget.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred)

        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__scan: Optional[scan_model.Scan] = None
        self.__timer = qt.QTimer(self)
        self.__timer.setInterval(1000)
        self.__timer.timeout.connect(self.__updateRemaining)
        self.__updateNoScan()
        self.__start: Optional(float) = None
        self.__end: Optional(float) = None

    def setFlintModel(self, flintModel: flint_model.FlintState = None):
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.disconnect(self.__currentScanChanged)
            self.__setScan(None)
        self.__flintModel = flintModel
        if self.__flintModel is not None:
            self.__flintModel.currentScanChanged.connect(self.__currentScanChanged)
            self.__setScan(self.__flintModel.currentScan())

    def __currentScanChanged(self):
        self.__setScan(self.__flintModel.currentScan())

    def __setScan(self, scan: scan_model.Scan = None):
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
                self.__updateRemaining()
                if not self.__timer.isActive():
                    self.__timer.start()
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

        if scan is None or scan.state() != scan_model.ScanState.PROCESSING:
            if self.__timer.isActive():
                self.__timer.stop()

    def __updateNoScan(self):
        self.__widget.scanInfo.setText("No scan available")
        self.__widget.process.setVisible(False)
        self.__widget.noAcquisition.setVisible(True)
        self.__widget.noAcquisition.setText("NO SCAN")
        self.__widget.remainingTime.setText("")
        if self.__timer.isActive():
            self.__timer.stop()

    def __updateScanInfo(self):
        scan = self.__scan
        assert scan is not None
        title = scan_info_helper.get_full_title(scan)
        self.__widget.scanInfo.setText(title)

        # estimation = scan_info.get('estimation')
        # ex: {'total_motion_time': 2.298404048112306, 'total_count_time': 0.1, 'total_time': 2.398404048112306}
        scan_info = scan.scanInfo()
        totalTime = scan_info.get("estimation", {}).get("total_time", None)
        if totalTime is not None:
            self.__end = self.__start + totalTime
        else:
            self.__end = None
            self.__widget.process.setEnabled(False)
            self.__widget.remainingTime.setText("No estimation time")

    def __updateRemaining(self):
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
