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
import scipy.signal

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

        print("Acquisition started")
        self.__timer = qt.QTimer(self)
        self.__timer.timeout.connect(self.updateNewData)
        self.__timer.start(interval)

    def scan(self) -> scan_model.Scan:
        if self.__scan is None:
            raise ValueError("Acquisition scan not started")
        return self.__scan

    def registerData(
        self, periode: int, channel: scan_model.Channel, data: numpy.ndarray
    ):
        if periode not in self.__data:
            self.__data[periode] = {}
        self.__data[periode][channel] = data

    def __createCounters(self, scan: scan_model.Scan, interval, duration):
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
        device1_channel3 = scan_model.Channel(device1)
        device1_channel3.setName("dev1:badsize")

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

        # Every 2 ticks
        nbPoints1 = (duration // interval) // 2
        index1 = numpy.linspace(0, duration, nbPoints1)
        # Every 3 ticks
        nbPoints2 = (duration // interval) // 3
        index2 = numpy.linspace(0, duration, nbPoints2)

        def step(position, nbPoints, gaussianStd, height=1):
            gaussianSize = int(gaussianStd) * 10
            gaussianData = scipy.signal.gaussian(gaussianSize, gaussianStd)
            stepData = numpy.zeros(len(index1) + gaussianSize)
            stepData[int(position) :] = 1
            stepData = scipy.signal.convolve(stepData, gaussianData, mode="same")[
                0:nbPoints
            ]
            stepData *= 1 / stepData[-1]
            return height * stepData

        pos = numpy.random.rand() * (nbPoints1 // 2) + nbPoints1 // 4
        height = 5 * numpy.random.rand() * 5
        stepData = (
            step(pos, nbPoints1, 6, height=height) + numpy.random.random(nbPoints1) * 1
        )

        self.registerData(2, master_time1_index, index1)

        data = numpy.sin(2 * numpy.pi * index1 / duration) + 0.1 * numpy.random.random(
            nbPoints1
        )
        self.registerData(2, device1_channel1, data)
        self.registerData(2, device1_channel2, numpy.random.random(nbPoints1))
        self.registerData(2, device1_channel3, numpy.random.random(nbPoints1 // 2))
        data = numpy.array([1.5] * nbPoints1 + 0.2 * numpy.random.random(nbPoints1))
        self.registerData(2, device2_channel1, data)
        self.registerData(2, device4_channel1, stepData)
        self.registerData(3, master_time2_index, index2)
        data = 0.5 * numpy.sin(2 * numpy.pi * index2 / duration) * numpy.cos(
            2 * numpy.pi * index2 / duration
        ) + 0.3 * numpy.random.random(nbPoints2)
        self.registerData(3, device3_channel1, data)

    def __createMcas(self, scan: scan_model.Scan, interval, duration):
        master_time1 = scan_model.Device(scan)
        master_time1.setName("timeMca")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timeMca:index")

        mca1 = scan_model.Device(scan)
        mca1.setName("mca1")
        mca1.setMaster(master_time1)
        mca2 = scan_model.Device(scan)
        mca2.setName("mca2")
        mca2.setMaster(master_time1)

        mca1_channel1 = scan_model.Channel(mca1)
        mca1_channel1.setName("mca1:chan1")
        mca1_channel1.setType(scan_model.ChannelType.SPECTRUM)
        mca1_channel2 = scan_model.Channel(mca1)
        mca1_channel2.setName("mca1:chan2")
        mca1_channel2.setType(scan_model.ChannelType.SPECTRUM)
        mca2_channel1 = scan_model.Channel(mca2)
        mca2_channel1.setName("mca2:chan1")
        mca2_channel1.setType(scan_model.ChannelType.SPECTRUM)
        mca2_channel2 = scan_model.Channel(mca2)
        mca2_channel2.setName("mca2:chan2")
        mca2_channel2.setType(scan_model.ChannelType.SPECTRUM)

        periode = 10
        nbPoints1 = (duration // interval) // periode + 1
        index1 = numpy.linspace(0, duration, nbPoints1)

        t, _ = numpy.ogrid[: len(index1), : len(index1)]
        raw_data1 = scipy.signal.gaussian(128, std=13) * t
        raw_data2 = scipy.signal.gaussian(100, std=12) * t

        self.registerData(periode, master_time1_index, index1)
        data = numpy.random.poisson(raw_data1)
        self.registerData(periode, mca1_channel1, data)
        data = numpy.random.poisson(raw_data1 * 0.9)
        self.registerData(periode, mca1_channel2, data)
        data = numpy.random.poisson(raw_data2 * 0.5)
        self.registerData(periode, mca2_channel1, data)
        data = numpy.random.poisson(raw_data2 * 0.5)
        self.registerData(periode, mca2_channel2, data)

    def __createImages(self, scan: scan_model.Scan, interval, duration):
        master_time1 = scan_model.Device(scan)
        master_time1.setName("timeImage")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timeImage:index")

        lima1 = scan_model.Device(scan)
        lima1.setName("lima1")
        lima1.setMaster(master_time1)
        lima2 = scan_model.Device(scan)
        lima2.setName("lima2")
        lima2.setMaster(master_time1)

        lima1_channel1 = scan_model.Channel(lima1)
        lima1_channel1.setName("lima1:image")
        lima1_channel1.setType(scan_model.ChannelType.IMAGE)
        lima2_channel1 = scan_model.Channel(lima2)
        lima2_channel1.setName("lima2:image")
        lima2_channel1.setType(scan_model.ChannelType.IMAGE)

        periode = 10

        nbPoints1 = (duration // interval) // periode + 1
        index1 = numpy.linspace(0, duration, nbPoints1)
        self.registerData(periode, master_time1_index, index1)

        size = 128
        lut = scipy.signal.gaussian(size, std=13) * 5
        yy, xx = numpy.ogrid[:size, :size]
        singleImage = lut[yy] * lut[xx]
        data = [numpy.random.poisson(singleImage) for _ in range(5)]
        data = numpy.array(data)
        self.registerData(periode, lima1_channel1, data)

        size = 256
        lut = scipy.signal.gaussian(size, std=8) * 10
        yy, xx = numpy.ogrid[:size, :size]
        singleImage = lut[yy] * lut[xx]
        data = [numpy.random.poisson(singleImage) for _ in range(5)]
        data = numpy.array(data)
        self.registerData(periode, lima2_channel1, data)

    def __createScatters(self, scan: scan_model.Scan, interval, duration):

        master_time1 = scan_model.Device(scan)
        master_time1.setName("time_scatter")

        device1 = scan_model.Device(scan)
        device1.setName("motor1")
        device1.setMaster(master_time1)
        device1_channel1 = scan_model.Channel(device1)
        device1_channel1.setName("motor1:position")

        device2 = scan_model.Device(scan)
        device2.setName("motor2")
        device2.setMaster(master_time1)
        device2_channel1 = scan_model.Channel(device2)
        device2_channel1.setName("motor2:position")

        device3 = scan_model.Device(scan)
        device3.setName("diode1")
        device3.setMaster(master_time1)
        device3_channel1 = scan_model.Channel(device3)
        device3_channel1.setName("diode1:intensity")

        device4 = scan_model.Device(scan)
        device4.setName("temprature1")
        device4.setMaster(master_time1)
        device4_channel1 = scan_model.Channel(device4)
        device4_channel1.setName("temperature1:value")

        # Every 2 ticks
        nbPoints = duration // interval
        nbX = int(numpy.sqrt(nbPoints))
        nbY = nbPoints // nbX + 1

        # Motor position
        yy = numpy.atleast_2d(numpy.ones(nbY)).T
        xx = numpy.atleast_2d(numpy.ones(nbX))

        positionX = numpy.linspace(10, 50, nbX) * yy
        positionX = positionX.reshape(nbX * nbY)
        positionX = positionX + numpy.random.rand(len(positionX)) - 0.5

        positionY = numpy.atleast_2d(numpy.linspace(20, 60, nbY)).T * xx
        positionY = positionY.reshape(nbX * nbY)
        positionY = positionY + numpy.random.rand(len(positionY)) - 0.5

        self.registerData(1, device1_channel1, positionX)
        self.registerData(1, device2_channel1, positionY)

        # Diodes position
        lut = scipy.signal.gaussian(max(nbX, nbY), std=8) * 10
        yy, xx = numpy.ogrid[:nbY, :nbX]
        signal = lut[yy] * lut[xx]
        diode1 = numpy.random.poisson(signal * 10)
        diode1 = diode1.reshape(nbX * nbY)
        self.registerData(1, device3_channel1, diode1)

        temperature1 = 25 + numpy.random.rand(nbX * nbY) * 5
        self.registerData(1, device4_channel1, temperature1)

    def __createScan(self, interval, duration) -> scan_model.Scan:
        self.__data = {}
        print("Preparing data...")
        scan = scan_model.Scan(None)
        self.__createCounters(scan, interval, duration)
        self.__createMcas(scan, interval, duration)
        self.__createImages(scan, interval, duration)
        self.__createScatters(scan, interval, duration)
        scan.seal()
        print("Data prepared")

        return scan

    def updateNewData(self):
        self.__tick += 1
        for modulo, data in self.__data.items():
            if (self.__tick % modulo) != 0:
                continue
            pos = self.__tick // modulo
            for channel, array in data.items():
                if channel.type() == scan_model.ChannelType.COUNTER:
                    # growing 1d data
                    p = min(len(array), pos)
                    newData = scan_model.Data(channel, array[0:p])
                elif channel.type() == scan_model.ChannelType.SPECTRUM:
                    # 1d data in an indexed array
                    newData = scan_model.Data(channel, array[pos])
                elif channel.type() == scan_model.ChannelType.IMAGE:
                    # image in a looped buffer
                    p = pos % len(array)
                    newData = scan_model.Data(channel, array[p])
                else:
                    assert False
                channel.setData(newData)

        self.__scan._fireScanDataUpdated()

        if self.__tick * self.__interval >= self.__duration:
            self.__scan.scanFinished.emit()
            self.__timer.stop()
            self.__timer.timeout.disconnect(self.updateNewData)
            self.__timer.deleteLater()
            self.__timer = None
            print("Acquisition finished")
