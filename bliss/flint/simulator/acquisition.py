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
import logging
import scipy.signal

from bliss.flint.model import scan_model
from bliss.flint.model import flint_model
from bliss.flint.helper import scan_manager


_logger = logging.getLogger(__name__)


class ChannelDataNodeMock:
    def __init__(self, array=None, image=None):
        self.__array = array
        self.__image = image
        self.from_stream = False

    def get(self, id):
        if self.__image is not None:
            return self
        return self.__array

    def get_image(self, id):
        return self.__image


class AcquisitionSimulator(qt.QObject):
    def __init__(self, parent=None):
        super(AcquisitionSimulator, self).__init__(parent=parent)
        self.__timer: Optional[qt.QTimer] = None
        self.__flintModel: Optional[flint_model.FlintState] = None
        self.__scan: Optional[scan_model.Scan] = None
        self.__scan_manager: Optional[scan_manager.ScanManager] = None
        self.__scanNb = 0
        self.__tick: int = 0
        self.__duration: int = 0
        self.__interval: int = 0
        self.__data: Dict[int, Dict[scan_model.Channel, numpy.ndarray]] = {}
        self.__scan_info = {}

    def setFlintModel(self, flintModel: flint_model.FlintState):
        self.__flintModel = flintModel

    def setScanManager(self, scanManager: scan_manager.ScanManager):
        self.__scan_manager = scanManager

    def start(self, interval: int, duration: int, name=None):
        if self.__timer is not None:
            print("Already scanning")
            return

        self.__tick = 0
        self.__duration = duration
        self.__interval = interval
        durationSecond = (duration / 1000) * 2
        self.__scan_info = {
            "acquisition_chain": {},
            "title": "foo",
            "scan_nb": self.__scanNb,
            "node_name": "scan" + str(self.__scanNb),
        }
        self.__scanNb += 1

        scan = self.__createScan(interval, duration, name)
        self.__scan = scan

        if self.__flintModel is not None:
            self.__flintModel.setCurrentScan(scan)
            scan.scanStarted.emit()

        if self.__scan_manager is not None:
            self.__scan_manager.new_scan(self.__scan_info)

        print("Acquisition started")
        self.__timer = qt.QTimer(self)
        self.__timer.timeout.connect(self.safeUpdateNewData)
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

    def __createCounters(
        self, scan: scan_model.Scan, interval, duration, includeMasters=True
    ):
        master_time1 = scan_model.Device(scan)
        master_time1.setName("timer")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer:elapsed_time")

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

        scan_info = {
            "display_names": {},
            "master": {
                "display_names": {},
                "images": [],
                "scalars": [],
                "scalars_units": {},
                "spectra": [],
            },
            "scalars": [
                device1_channel1.name(),
                device1_channel2.name(),
                device1_channel3.name(),
                device2_channel1.name(),
            ],
            "scalars_units": {},
        }
        if includeMasters:
            scan_info["master"]["scalars"].append(master_time1_index.name())
            scan_info["master"]["scalars_units"][master_time1_index.name()] = "s"
        else:
            scan_info["scalars"].append(master_time1_index.name())
            scan_info["scalars_units"][master_time1_index.name()] = "s"

        self.__scan_info["acquisition_chain"][master_time1.name()] = scan_info

        scan_info = {
            "display_names": {},
            "master": {
                "display_names": {},
                "images": [],
                "scalars": [master_time2_index.name()],
                "scalars_units": {master_time2_index.name(): "s"},
                "spectra": [],
            },
            "scalars": [device3_channel1.name(), device4_channel1.name()],
            "scalars_units": {},
        }
        self.__scan_info["acquisition_chain"][master_time2.name()] = scan_info

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
        master_time1.setName("timer_mca")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer_mca:elapsed_time")

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

        scan_info = {
            "display_names": {},
            "master": {
                "display_names": {},
                "images": [],
                "scalars": [master_time1_index.name()],
                "scalars_units": {master_time1_index.name(): "s"},
                "spectra": [],
            },
            "spectra": [
                mca1_channel1.name(),
                mca1_channel2.name(),
                mca2_channel1.name(),
                mca2_channel2.name(),
            ],
            "scalars": [],
            "scalars_units": {},
        }
        self.__scan_info["acquisition_chain"][master_time1.name()] = scan_info

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
        master_time1.setName("timer_image")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer_image:elapsed_time")

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

        scan_info = {
            "display_names": {},
            "master": {
                "display_names": {},
                "images": [],
                "scalars": [master_time1_index.name()],
                "scalars_units": {master_time1_index.name(): "s"},
                "spectra": [],
            },
            "images": [lima1_channel1.name(), lima2_channel1.name()],
            "scalars": [],
            "scalars_units": {},
        }
        self.__scan_info["acquisition_chain"][master_time1.name()] = scan_info

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
        master_time1.setName("timer_scatter")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer_scatter:elapsed_time")

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

        scan_info = {
            "display_names": {},
            "master": {
                "display_names": {
                    device1_channel1.name(): device1.name(),
                    device2_channel1.name(): device2.name(),
                },
                "images": [],
                "scalars": [device1_channel1.name(), device2_channel1.name()],
                "scalars_units": {
                    device2_channel1.name(): "mm",
                    device3_channel1.name(): "mm",
                },
                "spectra": [],
            },
            "scalars": [
                device3_channel1.name(),
                device4_channel1.name(),
                master_time1_index.name(),
            ],
            "scalars_units": {master_time1_index.name(): "s"},
        }
        self.__scan_info["acquisition_chain"][master_time1.name()] = scan_info
        self.__scan_info["data_dim"] = 2

        # Every 2 ticks
        nbPoints = duration // interval
        nbX = int(numpy.sqrt(nbPoints))
        nbY = nbPoints // nbX + 1

        # Time base
        index1 = numpy.linspace(0, duration, nbPoints)
        self.registerData(1, master_time1_index, index1)

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

    def __createScan(self, interval, duration, name=None) -> scan_model.Scan:
        self.__data = {}
        print("Preparing data...")
        scan = scan_model.Scan(None)
        if name is None or name == "counter":
            self.__createCounters(scan, interval, duration)
        elif name == "counter-no-master":
            self.__createCounters(scan, interval, duration, includeMasters=False)
        if name is None or name == "mca":
            self.__createMcas(scan, interval, duration)
        if name is None or name == "image":
            self.__createImages(scan, interval, duration)
        if name is None or name == "scatter":
            self.__createScatters(scan, interval, duration)
        scan.seal()

        if len(self.__data) == 0:
            raise ValueError("name (%s) maybe not valid" % name)

        print("Data prepared")

        return scan

    def safeUpdateNewData(self):
        try:
            self.updateNewData()
        except:
            _logger.error("Error while updating data", exc_info=True)
            self.__endOfScan()

    def updateNewData(self):
        self.__tick += 1
        channel_scan_data = {}
        for modulo, data in self.__data.items():
            if (self.__tick % modulo) != 0:
                continue
            pos = self.__tick // modulo
            for channel, array in data.items():
                if channel.type() == scan_model.ChannelType.COUNTER:
                    # growing 1d data
                    p = min(len(array), pos)
                    array = array[0:p]
                    newData = scan_model.Data(channel, array)
                    channel_scan_data[channel.name()] = array
                elif channel.type() == scan_model.ChannelType.SPECTRUM:
                    # 1d data in an indexed array
                    array = array[pos]
                    newData = scan_model.Data(channel, array)
                    if self.__scan_manager is not None:
                        scan_data = {
                            "scan_info": self.__scan_info,
                            "channel_name": channel.name(),
                            "channel_data_node": ChannelDataNodeMock(array=array),
                            "channel_index": 0,
                        }
                        self.__scan_manager.new_scan_data(
                            "1d", channel.master().name(), scan_data
                        )
                elif channel.type() == scan_model.ChannelType.IMAGE:
                    # image in a looped buffer
                    p = pos % len(array)
                    array = array[p]
                    newData = scan_model.Data(channel, array)
                    if self.__scan_manager is not None:
                        scan_data = {
                            "scan_info": self.__scan_info,
                            "channel_name": channel.name(),
                            "channel_data_node": ChannelDataNodeMock(image=array),
                            "channel_index": 0,
                        }
                        self.__scan_manager.new_scan_data(
                            "2d", channel.master().name(), scan_data
                        )
                else:
                    assert False
                channel.setData(newData)

        if self.__scan_manager is not None:
            if len(channel_scan_data) > 0:
                scan_data = {"data": channel_scan_data, "scan_info": self.__scan_info}
                self.__scan_manager.new_scan_data("0d", "foo", scan_data)

        if self.__flintModel is not None:
            self.__scan._fireScanDataUpdated()

        if self.__tick * self.__interval >= self.__duration:
            self.__timer.stop()
            qt.QTimer.singleShot(10, self.__endOfScan)

    def __endOfScan(self):
        self.__scan.scanFinished.emit()
        self.__timer.timeout.disconnect(self.safeUpdateNewData)
        self.__timer.deleteLater()
        self.__timer = None
        if self.__scan_manager is not None:
            self.__scan_manager.end_scan(self.__scan_info)
        print("Acquisition finished")
