# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Tuple
from typing import Union
from typing import Optional
from typing import Dict
from typing import List

import gevent
from silx.gui import qt

from bliss.flint.model import flint_model
from bliss.flint.simulator.acquisition import AcquisitionSimulator


class SimulatorWidget(qt.QMainWindow):
    def __init__(self, parent: qt.QWidget = None):
        super(SimulatorWidget, self).__init__(parent=parent)
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
        button.setText("Scatter scan")
        button.clicked.connect(lambda: self.__startScan(10, 2000, "scatter"))
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
        gevent.spawn(flint.select_shapes, plotId)

    def __startScan(self, interval: int, duration: int, name=None):
        if self.__simulator is None:
            return
        self.__simulator.start(interval, duration, name)

    def setSimulator(self, simulator: AcquisitionSimulator):
        self.__simulator = simulator
