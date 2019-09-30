# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Dict
from typing import Optional

from silx.gui import qt

import numpy
from scipy import signal

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model


class AcquisitionSimulator(qt.QObject):
    def __init__(self, parent=None):
        super(AcquisitionSimulator, self).__init__(parent=parent)
        self.__timer: Optional[qt.QTimer] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__scan: Optional[scan_model.Scan] = None
        self.__tick: int = 0
        self.__duration: int = 0
        self.__interval: int = 0
        self.__data: Dict[int, Dict[scan_model.Channel, numpy.ndarray]] = {}

    def setFlintModel(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel

    def start(self, interval: int, duration: int):
        assert self.__flintModel is not None
        if self.__timer is not None:
            print("Already scanning")
            return

        self.__tick = 0
        self.__duration = duration
        self.__interval = interval

        scan = self.__createScan(interval, duration)
        self.__scan = scan

        self.__flintModel.setCurrentScan(scan)
        scan.scanStarted.emit()

        self.__timer = qt.QTimer(self)
        self.__timer.timeout.connect(self.updateNewData)
        self.__timer.start(interval)

    def scan(self) -> scan_model.Scan:
        if self.__scan is None:
            raise ValueError("Acquisition scan not started")
        return self.__scan

    def __createScan(self, interval, duration) -> scan_model.Scan:
        scan = scan_model.Scan(None)

        master_time1 = scan_model.Device(scan)
        master_time1.setName("time")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("time:index")

        device1 = scan_model.Device(scan)
        device1.setName("dev1")
        device1.setMaster(master_time1)
        device1_channel1 = scan_model.Channel(device1)
        device1_channel1.setName("dev1:chan1")
        device1_channel2 = scan_model.Channel(device1)
        device1_channel2.setName("dev1:chan2")

        device2 = scan_model.Device(scan)
        device2.setName("dev2")
        device2.setMaster(master_time1)
        device2_channel1 = scan_model.Channel(device2)
        device2_channel1.setName("dev2:chan1")

        master_time2 = scan_model.Device(scan)
        master_time2.setName("time2")
        master_time2_index = scan_model.Channel(master_time2)
        master_time2_index.setName("time2:index")

        device3 = scan_model.Device(scan)
        device3.setName("dev3")
        device3.setMaster(master_time2)
        device3_channel1 = scan_model.Channel(device3)
        device3_channel1.setName("dev3:chan1")

        device4 = scan_model.Device(scan)
        device4.setName("dev4")
        device4_channel1 = scan_model.Channel(device4)
        device4_channel1.setName("dev4:chan1")

        scan.seal()

        # Every 2 ticks
        nbPoints1 = (duration // interval) // 2
        index1 = numpy.linspace(0, duration, nbPoints1)
        # Every 3 ticks
        nbPoints2 = (duration // interval) // 3
        index2 = numpy.linspace(0, duration, nbPoints2)

        self.__data = {}

        def step(position, nbPoints, gaussianStd, height=1):
            gaussianSize = int(gaussianStd) * 10
            gaussianData = signal.gaussian(gaussianSize, gaussianStd)
            stepData = numpy.zeros(len(index1) + gaussianSize)
            stepData[int(position) :] = 1
            stepData = signal.convolve(stepData, gaussianData, mode="same")[0:nbPoints]
            stepData *= 1 / stepData[-1]
            return height * stepData

        pos = numpy.random.rand() * (nbPoints1 // 2) + nbPoints1 // 4
        height = 5 * numpy.random.rand() * 5
        stepData = (
            step(pos, nbPoints1, 6, height=height) + numpy.random.random(nbPoints1) * 1
        )

        self.__data[2] = {
            master_time1_index: index1,
            device1_channel1: numpy.sin(2 * numpy.pi * index1 / duration)
            + 0.1 * numpy.random.random(nbPoints1),
            device1_channel2: numpy.random.random(nbPoints1),
            device2_channel1: numpy.array(
                [1.5] * nbPoints1 + 0.2 * numpy.random.random(nbPoints1)
            ),
            device4_channel1: stepData,
        }
        self.__data[3] = {
            master_time2_index: index2,
            device3_channel1: 0.5
            * numpy.sin(2 * numpy.pi * index2 / duration)
            * numpy.cos(2 * numpy.pi * index2 / duration)
            + 0.3 * numpy.random.random(nbPoints2),
        }
        return scan

    def updateNewData(self):
        self.__tick += 1
        for modulo, data in self.__data.items():
            if (self.__tick % modulo) != 0:
                continue
            pos = self.__tick // modulo
            for channel, array in data.items():
                newData = scan_model.Data(channel, array[0:pos])
                channel.setData(newData)

        self.__scan._fireScanDataUpdated()

        if self.__tick * self.__interval >= self.__duration:
            self.__scan.scanFinished.emit()
            self.__timer.stop()
            self.__timer.timeout.disconnect(self.updateNewData)
            self.__timer.deleteLater()
            self.__timer = None
