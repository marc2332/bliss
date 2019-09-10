# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
from typing import List

from silx.gui import qt
import numpy


class Scan(qt.QObject):

    scanStarted = qt.Signal()
    scanSuccessed = qt.Signal()
    scanFailed = qt.Signal()
    scanFinished = qt.Signal()
    scanDataUpdated = qt.Signal()

    def __init__(self, parent=None, devices: List[Device] = None):
        if devices is None:
            devices = []
        super(Scan, self).__init__(parent=parent)
        self.__devices = devices
        self.__channels = {}
        self.__cacheChannels()
        self.__cacheData = {}

    def _fireScanDataUpdated(self):
        self.__cacheData = {}
        self.scanDataUpdated.emit()

    def __cacheChannels(self):
        self.__channels.clear()
        for device in self.__devices:
            for channel in device.channels():
                name = channel.name()
                self.__channels[name] = channel

    def devices(self) -> List[Device]:
        # FIXME better to export iterator or read only list
        return self.__devices

    def getChannelByName(self, name) -> Union[None, Channel]:
        return self.__channels.get(name, None)

    def hasCachedResult(self, obj: object) -> bool:
        return obj in self.__cacheData

    def getCachedResult(self, obj: object):
        return self.__cacheData[obj]

    def setCachedResult(self, obj: object, result):
        self.__cacheData[obj] = result


class Device(qt.QObject):
    def __init__(
        self,
        parent=None,
        name=None,
        channels: List[Channel] = None,
        master: Union[None, Channel] = None,
    ):
        if channels is None:
            channels = []
        super(Device, self).__init__(parent=parent)
        self.__name = name
        self.__channels = channels
        self.__master = master

    def name(self) -> str:
        return self.__name

    def channels(self) -> List[Channel]:
        # FIXME better to export iterator or read only list
        return self.__channels


class Channel(qt.QObject):

    dataUpdated = qt.Signal(object)

    def __init__(self, parent=None, name: str = None):
        super(Channel, self).__init__(parent=parent)
        self.__data = None
        self.__name = name

    def name(self) -> str:
        return self.__name

    def hasData(self) -> bool:
        return self.__data is not None

    def data(self) -> Data:
        return self.__data

    def setData(self, data: Data):
        self.__data = data
        self.dataUpdated.emit(data)


class Data(qt.QObject):
    def __init__(self, parent=None, array: numpy.ndarray = None):
        super(Data, self).__init__(parent=parent)
        self.__array = array

    def array(self) -> numpy.ndarray:
        return self.__array
