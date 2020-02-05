# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional

import gevent
import logging
from silx.gui import qt

from bliss.flint.model import flint_model
from bliss.flint.simulator.acquisition import AcquisitionSimulator

_logger = logging.getLogger(__name__)


class SimulatorWidget(qt.QMainWindow):
    def __init__(self, parent: qt.QWidget = None):
        flags = qt.Qt.WindowStaysOnTopHint
        super(SimulatorWidget, self).__init__(parent=parent, flags=flags)
        self.setWindowTitle("Simulator")
        self.__simulator: Optional[AcquisitionSimulator] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__initLayout()

    def __initLayout(self):
        panel = qt.QWidget()
        layout = qt.QVBoxLayout(panel)

        button = qt.QPushButton(self)
        button.setText("Counter scan")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "counter"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("Slit scan")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "slit"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("Counter scan (no masters)")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "counter-no-master"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("Scatter scan")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "scatter"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("Scatter 1000x1000 scan")
        button.clicked.connect(lambda: self.__startScan(10, 20000, "scatter-big"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("MCA scan")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "mca"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("Image scan")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "image"))
        layout.addWidget(button)

        button = qt.QPushButton(self)
        button.setText("Edit lima1:image ROIs")
        button.clicked.connect(lambda: self.__editRoi("lima1:image"))
        layout.addWidget(button)

        self.setCentralWidget(panel)

    def setFlintModel(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel

    def __editRoi(self, channelName):
        flint = self.__flintModel.flintApi()
        plotId = flint.get_live_scan_plot(channelName, "image")
        gevent.spawn(flint.request_select_shapes, plotId)

    def __startScan(self, interval: int, duration: int, name=None):
        if self.__simulator is None:
            return
        try:
            self.__simulator.start(interval, duration, name)
        except:
            _logger.error("Error while starting scan", exc_info=True)

    def setSimulator(self, simulator: AcquisitionSimulator):
        self.__simulator = simulator
