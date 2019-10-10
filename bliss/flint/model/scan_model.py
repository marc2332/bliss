# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import List
from typing import Iterator
from typing import Dict
from typing import Any

import logging
import numpy
import enum

from silx.gui import qt


_logger = logging.getLogger(__name__)


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
        qt.QObject.__init__(self, parent=parent)
        _Sealable.__init__(self)
        self.__devices: List[Device] = []
        self.__channels: Dict[str, Channel] = {}
        self.__cacheData: Dict[Any, Any] = {}
        self.__cacheMessage: Dict[Any, Any] = {}

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
        self.__cacheMessage = {}
        self.scanDataUpdated.emit()

    def __cacheChannels(self, device: Device):
        for channel in device.channels():
            name = channel.name()
            if name in self.__channels:
                _logger.error("Channel named %s is registered 2 times", name)
            self.__channels[name] = channel

    def devices(self) -> Iterator[Device]:
        # FIXME better to export iterator or read only list
        return iter(self.__devices)

    def getChannelByName(self, name) -> Optional[Channel]:
        return self.__channels.get(name, None)

    def hasCachedResult(self, obj: Any) -> bool:
        return obj in self.__cacheData

    def getCachedResult(self, obj: Any):
        return self.__cacheData[obj]

    def setCachedResult(self, obj: Any, result: Any):
        self.__cacheData[obj] = result

    def hasCacheValidation(self, obj: Any, version: int):
        result = self.__cacheMessage.get(obj, None)
        if result is None:
            return False
        if result[0] != version:
            del self.__cacheMessage[obj]
            return False
        return True

    def setCacheValidation(self, obj: Any, version: int, result: Optional[str]):
        self.__cacheMessage[obj] = (version, result)

    def getCacheValidation(self, obj: Any, version: int):
        result = self.__cacheMessage[obj]
        if result[0] != version:
            raise KeyError("Version do not match")
        return result[1]


class Device(qt.QObject, _Sealable):
    def __init__(self, parent: Scan):
        qt.QObject.__init__(self, parent=parent)
        _Sealable.__init__(self)
        self.__name: str = ""
        self.__channels: List[Channel] = []
        self.__master: Optional[Device] = None
        self.__topMaster: Optional[Device] = None
        parent.addDevice(self)

    def scan(self) -> Scan:
        return self.parent()

    def seal(self):
        for channel in self.__channels:
            channel.seal()
        super(Device, self).seal()

    def setName(self, name: str):
        if self.isSealed():
            raise SealedError()
        self.__name = name

    def name(self) -> str:
        return self.__name

    def addChannel(self, channel: Channel):
        if self.isSealed():
            raise SealedError()
        if channel in self.__channels:
            raise ValueError("Already in the channel list")
        self.__channels.append(channel)

    def channels(self) -> Iterator[Channel]:
        # FIXME better to export iterator or read only list
        return iter(self.__channels)

    def setMaster(self, master: Optional[Device]):
        if self.isSealed():
            raise SealedError()
        self.__master = master
        self.__topMaster = None

    def master(self) -> Optional[Device]:
        return self.__master

    def topMaster(self) -> Device:
        if self.__topMaster is None:
            topMaster = self
            while topMaster:
                m = topMaster.master()
                if m is None:
                    break
                topMaster = m
            self.__topMaster = topMaster
        return self.__topMaster

    def isMaster(self) -> bool:
        """
        True if the device is a master device.
        """
        # FIXME: This have to be improved
        return self.__master is None


class ChannelType(enum.Enum):
    COUNTER = 0
    SPECTRUM = 1
    IMAGE = 2


class Channel(qt.QObject, _Sealable):

    dataUpdated = qt.Signal(object)

    def __init__(self, parent: Device):
        qt.QObject.__init__(self, parent=parent)
        _Sealable.__init__(self)
        self.__data: Optional[Data] = None
        self.__name: str = ""
        self.__type: ChannelType = ChannelType.COUNTER
        parent.addChannel(self)

    def setType(self, channelType: ChannelType):
        if self.isSealed():
            raise SealedError()
        self.__type = channelType

    def type(self) -> ChannelType:
        return self.__type

    def device(self) -> Device:
        return self.parent()

    def name(self) -> str:
        return self.__name

    def baseName(self):
        return self.__name.split(":")[-1]

    @property
    def ndim(self) -> int:
        """
        Returns the amount of dimensions of the data, before reaching the data.

        Mimics numpy arrays."""
        if self.__type == ChannelType.COUNTER:
            # one value per count
            return 1
        elif self.__type == ChannelType.SPECTRUM:
            # one value per MCA channel
            return 1
        elif self.__type == ChannelType.IMAGE:
            return 2
        else:
            assert False

    def setName(self, name: str):
        if self.isSealed():
            raise SealedError()
        self.__name = name

    def hasData(self) -> bool:
        return self.__data is not None

    def data(self) -> Optional[Data]:
        return self.__data

    def isDataCompatible(self, data: Data):
        if data is None:
            return True
        if self.ndim != data.array().ndim:
            return False
        return True

    def setData(self, data: Data):
        # The only one attribute which can be updated
        if not self.isDataCompatible(data):
            raise ValueError("Data do not fit the channel requirements")
        self.__data = data
        self.dataUpdated.emit(data)


class Data(qt.QObject):
    def __init__(self, parent=None, array: numpy.ndarray = None):
        super(Data, self).__init__(parent=parent)
        self.__array = array

    def array(self) -> numpy.ndarray:
        return self.__array
