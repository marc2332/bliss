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


class SealedError(Exception):
    pass


class _Sealable:
    def __init__(self):
        self.__isSealed = False

    def seal(self):
        self.__isSealed = True

    def isSealed(self):
        return self.__isSealed


class Scan(qt.QObject, _Sealable):

    scanStarted = qt.Signal()
    scanSuccessed = qt.Signal()
    scanFailed = qt.Signal()
    scanFinished = qt.Signal()
    scanDataUpdated = qt.Signal()

    def __init__(self, parent=None):
        super(Scan, self).__init__(parent=parent)
        self.__devices = []
        self.__channels = {}
        self.__cacheData = {}

    def seal(self):
        self.__channels = {}
        for device in self.__devices:
            device.seal()
            self.__cacheChannels(device)
        super(Scan, self).seal()

    def addDevice(self, device: Device):
        if self.isSealed():
            raise SealedError()
        if device in self.__devices:
            raise ValueError("Already in the device list")
        self.__devices.append(device)

    def _fireScanDataUpdated(self):
        self.__cacheData = {}
        self.scanDataUpdated.emit()

    def __cacheChannels(self, device:Device):
        for channel in device.channels():
            name = channel.name()
            self.__channels[name] = channel

    def devices(self) -> List[Device]:
        # FIXME better to export iterator or read only list
        return iter(self.__devices)

    def getChannelByName(self, name) -> Union[None, Channel]:
        return self.__channels.get(name, None)

    def hasCachedResult(self, obj: object) -> bool:
        return obj in self.__cacheData

    def getCachedResult(self, obj: object):
        return self.__cacheData[obj]

    def setCachedResult(self, obj: object, result):
        self.__cacheData[obj] = result


class Device(qt.QObject, _Sealable):
    def __init__(self, parent:Scan):
        super(Device, self).__init__(parent=parent)
        self.__name = None
        self.__channels = []
        self.__master = None
        parent.addDevice(self)

    def seal(self):
        for channel in self.__channels:
            channel.seal()
        super(Device, self).seal()

    def setName(self, name:str):
        if self.isSealed():
            raise SealedError()
        self.__name = name

    def name(self) -> str:
        return self.__name

    def addChannel(self, channel:Channel):
        if self.isSealed():
            raise SealedError()
        if channel in self.__channels:
            raise ValueError("Already in the channel list")
        self.__channels.append(channel)

    def channels(self) -> List[Channel]:
        # FIXME better to export iterator or read only list
        return iter(self.__channels)

    def setMaster(self, master: Union[None,Device]):
        if self.isSealed():
            raise SealedError()
        self.__master = master

    def master(self) -> Device:
        return self.__master

    def isMaster(self) -> bool:
        """"
        True if the device is a master device.
        """
        # FIXME: This have to be improved1
        return self.__master is None


class Channel(qt.QObject, _Sealable):

    dataUpdated = qt.Signal(object)

    def __init__(self, parent:Device):
        super(Channel, self).__init__(parent=parent)
        self.__data = None
        self.__name = None
        parent.addChannel(self)

    def name(self) -> str:
        return self.__name

    def setName(self, name:str):
        if self.isSealed():
            raise SealedError()
        self.__name = name

    def hasData(self) -> bool:
        return self.__data is not None

    def data(self) -> Data:
        return self.__data

    def setData(self, data: Data):
        # The only one attribute which can be updated
        self.__data = data
        self.dataUpdated.emit(data)


class Data(qt.QObject):
    def __init__(self, parent=None, array: numpy.ndarray = None):
        super(Data, self).__init__(parent=parent)
        self.__array = array

    def array(self) -> numpy.ndarray:
        return self.__array
