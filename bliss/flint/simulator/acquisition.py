# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Dict
from typing import Optional
from typing import Any

import numpy
import time
import logging
import scipy.signal

from silx.gui import qt

from bliss.flint.model import scan_model
from bliss.flint.manager import scan_manager


_logger = logging.getLogger(__name__)


class _ChannelDataNodeMock:
    def __init__(self, array=None, image=None, last_index=None):
        self.__array = array
        self.__image = image
        self.__last_index = last_index
        self.from_stream = False

    def is_video_frame_have_meaning(self):
        return True

    @property
    def last_image_ready(self):
        return self.__last_index

    @property
    def last_index(self):
        return self.__last_index

    def get(self, id):
        if self.__image is not None:
            return self
        return self.__array

    def get_image(self, id):
        return self.__image

    def get_last_image(self, id):
        return self.__image

    def get_last_live_image(self):
        return self.__image, self.__last_index


class _VirtualScan:
    """Store data and simulate scan processing"""

    def __init__(self, parent, scanManager: scan_manager.ScanManager):
        self.__data: Dict[int, Dict[scan_model.Channel, numpy.ndarray]] = {}
        self.scan_info: Dict[str, Any] = {}
        self.__duration: int = 0
        self.__interval: int = 0
        self.__timer: Optional[qt.QTimer] = None
        self.__timer = qt.QTimer(parent)
        self.__timer.timeout.connect(self.safeProcessData)
        self.__scan_manager = scanManager
        self.__scan: scan_model.Scan = scan_model.Scan(None)
        self.__step = 1
        self.__patchCorner = True

    def setStep(self, step):
        """Size of each increment of data.

        Allow to send data by bunches.
        """
        self.__step = step

    def setDuration(self, duration: int):
        self.__duration = duration

    def setInterval(self, interval: int):
        self.__interval = interval

    def scan(self):
        return self.__scan

    def start(self):
        self.__scan.seal()

        if len(self.__data) == 0:
            raise ValueError("No data in this scan")

        self.__scan_manager.new_scan(self.scan_info)

        print("Acquisition started")
        self.__timer.start(self.__interval)
        self.__startTime = time.time()

    def isRunning(self):
        return self.__timer is not None

    def registerData(
        self, periode: int, channel: scan_model.Channel, data: numpy.ndarray
    ):
        if periode not in self.__data:
            self.__data[periode] = {}
        self.__data[periode][channel] = data

    def safeProcessData(self):
        try:
            self.processData()
        except:
            _logger.error("Error while updating data", exc_info=True)
            self.__endOfScan()

    def processData(self):
        duration = (time.time() - self.__startTime) * 1000
        tick = int(duration // self.__interval)

        channel_scan_data = {}
        for modulo, data in self.__data.items():
            if (tick % modulo) != 0:
                continue
            pos = (tick // modulo) * self.__step
            for channel, array in data.items():
                if channel.type() == scan_model.ChannelType.COUNTER:
                    # growing 1d data
                    p = min(len(array), pos)
                    array = array[0:p]
                    channel_scan_data[channel.name()] = array
                elif channel.type() == scan_model.ChannelType.SPECTRUM:
                    # 1d data in an indexed array
                    array = array[pos]
                    scan_data = {
                        "scan_info": self.scan_info,
                        "channel_name": channel.name(),
                        "channel_data_node": _ChannelDataNodeMock(array=array),
                        "channel_index": 0,
                    }
                    self.__scan_manager.new_scan_data(
                        "1d", channel.master().name(), scan_data
                    )
                elif channel.type() == scan_model.ChannelType.IMAGE:
                    # image in a looped buffer
                    p = pos % len(array)
                    array = array[p]
                    if self.__patchCorner:
                        array = numpy.array(array)
                        array[0, 0] = pos
                    scan_data = {
                        "scan_info": self.scan_info,
                        "channel_name": channel.name(),
                        "channel_data_node": _ChannelDataNodeMock(
                            image=array, last_index=pos
                        ),
                        "channel_index": 0,
                    }
                    self.__scan_manager.new_scan_data(
                        "2d", channel.master().name(), scan_data
                    )
                else:
                    assert False

        if len(channel_scan_data) > 0:
            scan_data = {"data": channel_scan_data, "scan_info": self.scan_info}
            self.__scan_manager.new_scan_data("0d", "foo", scan_data)

        if duration >= self.__duration:
            self.__timer.stop()
            qt.QTimer.singleShot(10, self.__endOfScan)

    def __endOfScan(self):
        self.__timer.timeout.disconnect(self.safeProcessData)
        self.__timer.deleteLater()
        self.__timer = None
        self.__scan_manager.end_scan(self.scan_info)
        print("Acquisition finished")


class AcquisitionSimulator(qt.QObject):
    def __init__(self, parent=None):
        super(AcquisitionSimulator, self).__init__(parent=parent)
        self.__scan_manager = scan_manager.ScanManager
        self.__scanNb = 0
        self.__scans = []

    def setScanManager(self, scanManager: scan_manager.ScanManager):
        self.__scan_manager = scanManager

    def start(self, interval: int, duration: int, name=None):
        scan = self.__createScan(interval, duration, name)

        # clean older
        scans = list(self.__scans)
        for s in scans:
            if not s.isRunning():
                self.__scans.remove(s)

        self.__scans.append(scan)
        scan.start()

    def scan(self) -> scan_model.Scan:
        if self.__scan is None:
            raise ValueError("Acquisition scan not started")
        return self.__scan

    def __createCounters(
        self, scan: _VirtualScan, interval, duration, includeMasters=True
    ):
        master_time1 = scan_model.Device(scan.scan())
        master_time1.setName("timer")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer:elapsed_time")

        device1 = scan_model.Device(scan.scan())
        device1.setName("dev1")
        device1.setMaster(master_time1)
        device1_channel1 = scan_model.Channel(device1)
        device1_channel1.setName("dev1:chan1")
        device1_channel2 = scan_model.Channel(device1)
        device1_channel2.setName("dev1:chan2")
        device1_channel3 = scan_model.Channel(device1)
        device1_channel3.setName("dev1:badsize")

        device2 = scan_model.Device(scan.scan())
        device2.setName("dev2")
        device2.setMaster(master_time1)
        device2_channel1 = scan_model.Channel(device2)
        device2_channel1.setName("dev2:chan1")

        master_time2 = scan_model.Device(scan.scan())
        master_time2.setName("time2")
        master_time2_index = scan_model.Channel(master_time2)
        master_time2_index.setName("time2:index")

        device3 = scan_model.Device(scan.scan())
        device3.setName("dev3")
        device3.setMaster(master_time2)
        device3_channel1 = scan_model.Channel(device3)
        device3_channel1.setName("dev3:chan1")

        device4 = scan_model.Device(scan.scan())
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

        scan.scan_info["acquisition_chain"][master_time1.name()] = scan_info

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
        scan.scan_info["acquisition_chain"][master_time2.name()] = scan_info

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
        height = 5 + numpy.random.rand() * 5
        stepData = (
            step(pos, nbPoints1, 6, height=height) + numpy.random.random(nbPoints1) * 1
        )

        scan.registerData(2, master_time1_index, index1)

        data = numpy.sin(2 * numpy.pi * index1 / duration) + 0.1 * numpy.random.random(
            nbPoints1
        )
        scan.registerData(2, device1_channel1, data)
        scan.registerData(2, device1_channel2, numpy.random.random(nbPoints1))
        scan.registerData(2, device1_channel3, numpy.random.random(nbPoints1 // 2))
        data = numpy.array([1.5] * nbPoints1 + 0.2 * numpy.random.random(nbPoints1))
        scan.registerData(2, device2_channel1, data)
        scan.registerData(2, device4_channel1, stepData)
        scan.registerData(3, master_time2_index, index2)
        data = 0.5 * numpy.sin(2 * numpy.pi * index2 / duration) * numpy.cos(
            2 * numpy.pi * index2 / duration
        ) + 0.3 * numpy.random.random(nbPoints2)
        scan.registerData(3, device3_channel1, data)

    def __createSlit(self, scan: _VirtualScan, interval, duration, includeMasters=True):
        master_time1 = scan_model.Device(scan.scan())
        master_time1.setName("timer")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer:elapsed_time")

        device1 = scan_model.Device(scan.scan())
        device1.setName("dev1")
        device1.setMaster(master_time1)
        device1_channel1 = scan_model.Channel(device1)
        device1_channel1.setName("dev1:sy")

        device2 = scan_model.Device(scan.scan())
        device2.setName("dev2")
        device2.setMaster(master_time1)
        device2_channel1 = scan_model.Channel(device2)
        device2_channel1.setName("dev2:diode1")
        device2_channel2 = scan_model.Channel(device2)
        device2_channel2.setName("dev2:diode2")

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
                device2_channel1.name(),
                device2_channel2.name(),
                master_time1_index.name(),
            ],
            "scalars_units": {},
        }

        start, stop = -10, 20

        if includeMasters:
            scan_info["master"]["scalars"].append(device1_channel1.name())
            scan_info["master"]["scalars_units"][device1_channel1.name()] = "mm"
        else:
            scan_info["scalars"].append(device1_channel1.name())
            scan_info["scalars_units"][device1_channel1.name()] = "mm"

        scan.scan_info["acquisition_chain"][master_time1.name()] = scan_info

        requests = {}
        requests[device1_channel1.name()] = {"start": start, "stop": stop}
        scan.scan_info["requests"] = requests

        # Every 2 ticks
        nbPoints1 = (duration // interval) // 2
        index1 = numpy.linspace(0, duration, nbPoints1)

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
        height = 5 + numpy.random.rand() * 5
        stepData = (
            step(pos, nbPoints1, 6, height=height) + numpy.random.random(nbPoints1) * 1
        )
        gaussianData = (
            scipy.signal.gaussian(nbPoints1, 6) * height
            + numpy.random.random(nbPoints1) * 1
        )

        motorData = (
            numpy.linspace(start, stop, nbPoints1)
            + numpy.random.random(nbPoints1) * 0.2
        )
        scan.registerData(2, master_time1_index, index1)
        scan.registerData(2, device1_channel1, motorData)
        scan.registerData(2, device2_channel1, stepData)
        scan.registerData(2, device2_channel2, gaussianData)

    def __createMcas(self, scan: _VirtualScan, interval, duration):
        master_time1 = scan_model.Device(scan.scan())
        master_time1.setName("timer_mca")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer_mca:elapsed_time")

        mca1 = scan_model.Device(scan.scan())
        mca1.setName("mca1")
        mca1.setMaster(master_time1)
        mca2 = scan_model.Device(scan.scan())
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
        scan.scan_info["acquisition_chain"][master_time1.name()] = scan_info

        periode = 10
        nbPoints1 = (duration // interval) // periode + 1
        index1 = numpy.linspace(0, duration, nbPoints1)

        t, _ = numpy.ogrid[: len(index1), : len(index1)]
        raw_data1 = scipy.signal.gaussian(128, std=13) * t
        raw_data2 = scipy.signal.gaussian(100, std=12) * t

        scan.registerData(periode, master_time1_index, index1)
        data = numpy.random.poisson(raw_data1)
        scan.registerData(periode, mca1_channel1, data)
        data = numpy.random.poisson(raw_data1 * 0.9)
        scan.registerData(periode, mca1_channel2, data)
        data = numpy.random.poisson(raw_data2 * 0.5)
        scan.registerData(periode, mca2_channel1, data)
        data = numpy.random.poisson(raw_data2 * 0.5)
        scan.registerData(periode, mca2_channel2, data)

    def __createImages(self, scan: _VirtualScan, interval, duration):
        master_time1 = scan_model.Device(scan.scan())
        master_time1.setName("timer_image")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer_image:elapsed_time")

        lima1 = scan_model.Device(scan.scan())
        lima1.setName("lima1")
        lima1.setMaster(master_time1)
        lima2 = scan_model.Device(scan.scan())
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
        scan.scan_info["acquisition_chain"][master_time1.name()] = scan_info

        periode = 10

        nbPoints1 = (duration // interval) // periode + 1
        index1 = numpy.linspace(0, duration, nbPoints1)
        scan.registerData(periode, master_time1_index, index1)

        size = 128
        lut = scipy.signal.gaussian(size, std=13) * 5
        yy, xx = numpy.ogrid[:size, :size]
        singleImage = lut[yy] * lut[xx]
        data = [numpy.random.poisson(singleImage) for _ in range(5)]
        data = numpy.array(data)
        scan.registerData(periode, lima1_channel1, data)

        size = 256
        lut = scipy.signal.gaussian(size, std=8) * 10
        yy, xx = numpy.ogrid[:size, :size]
        singleImage = lut[yy] * lut[xx]
        data = [numpy.random.poisson(singleImage) for _ in range(5)]
        data = numpy.array(data)
        scan.registerData(periode, lima2_channel1, data)

    def __createScatters(self, scan: _VirtualScan, interval, duration, size=None):

        master_time1 = scan_model.Device(scan.scan())
        master_time1.setName("timer_scatter")
        master_time1_index = scan_model.Channel(master_time1)
        master_time1_index.setName("timer_scatter:elapsed_time")

        device1 = scan_model.Device(scan.scan())
        device1.setName("motor1")
        device1.setMaster(master_time1)
        device1_channel1 = scan_model.Channel(device1)
        device1_channel1.setName("motor1:position")

        device2 = scan_model.Device(scan.scan())
        device2.setName("motor2")
        device2.setMaster(master_time1)
        device2_channel1 = scan_model.Channel(device2)
        device2_channel1.setName("motor2:position")

        device3 = scan_model.Device(scan.scan())
        device3.setName("diode1")
        device3.setMaster(master_time1)
        device3_channel1 = scan_model.Channel(device3)
        device3_channel1.setName("diode1:intensity")

        device4 = scan_model.Device(scan.scan())
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
        scan.scan_info["acquisition_chain"][master_time1.name()] = scan_info
        scan.scan_info["data_dim"] = 2

        # Every 2 ticks
        if size is None:
            nbPoints = duration // interval
        else:
            nbSteps = duration // interval
            nbPoints = size * size
            scan.setStep((nbPoints // nbSteps) + 1)
        nbX = int(numpy.sqrt(nbPoints))
        nbY = nbPoints // nbX + 1

        # Time base
        index1 = numpy.linspace(0, duration, nbPoints)
        scan.registerData(1, master_time1_index, index1)

        # Motor position
        yy = numpy.atleast_2d(numpy.ones(nbY)).T
        xx = numpy.atleast_2d(numpy.ones(nbX))

        # Dispertion
        dist = max(nbX, nbY)
        error = 1 / dist
        pixelSize = 20 / dist

        positionX = numpy.linspace(10, 50, nbX) * yy
        positionX = positionX.reshape(nbX * nbY)
        positionX = (
            positionX + (numpy.random.rand(len(positionX)) - 0.5) * pixelSize * 0.8
        )

        positionY = numpy.atleast_2d(numpy.linspace(20, 60, nbY)).T * xx
        positionY = positionY.reshape(nbX * nbY)
        positionY = (
            positionY + (numpy.random.rand(len(positionY)) - 0.5) * pixelSize * 0.8
        )

        scan.registerData(1, device1_channel1, positionX)
        scan.registerData(1, device2_channel1, positionY)

        # Diodes position
        lut = scipy.signal.gaussian(dist, std=0.8 * dist) * 10
        yy, xx = numpy.ogrid[:nbY, :nbX]
        signal = lut[yy] * lut[xx]
        diode1 = numpy.random.poisson(signal * dist)
        diode1 = diode1.reshape(nbX * nbY)
        scan.registerData(1, device3_channel1, diode1)

        temperature1 = 25 + numpy.random.rand(nbX * nbY) * 5 * error
        scan.registerData(1, device4_channel1, temperature1)

        requests = {}
        requests[device1_channel1.name()] = {
            "start": 10,
            "stop": 50,
            "points": nbX * nbY,
            "axis-points": nbX,
            "axis-kind": "fast",
        }
        requests[device2_channel1.name()] = {
            "start": 20,
            "stop": 60,
            "axis-points": nbY,
            "axis-kind": "slow",
        }
        scan.scan_info["requests"] = requests

    def __createScan(self, interval, duration, name=None) -> _VirtualScan:
        print("Preparing data...")

        scan = _VirtualScan(self, self.__scan_manager)
        scan.setDuration(duration)
        scan.setInterval(interval)

        scan.scan_info = {
            "acquisition_chain": {},
            "title": "foo",
            "scan_nb": self.__scanNb,
            "node_name": "scan" + str(self.__scanNb),
        }
        self.__scanNb += 1

        if name is None or name == "counter":
            self.__createCounters(scan, interval, duration)
        elif name is None or name == "slit":
            self.__createSlit(scan, interval, duration)
        elif name == "counter-no-master":
            self.__createCounters(scan, interval, duration, includeMasters=False)
        if name is None or name == "mca":
            self.__createMcas(scan, interval, duration)
        if name is None or name == "image":
            self.__createImages(scan, interval, duration)
        if name is None or name == "scatter":
            self.__createScatters(scan, interval, duration)
        if name == "scatter-big":
            self.__createScatters(scan, interval, duration, size=1000)

        print("Data prepared")
        return scan
