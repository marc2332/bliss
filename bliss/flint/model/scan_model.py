# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""This module provides object to model a scan acquisition process.

This tree structure is supposed to be real-only when a scan was
started. During the scan, only data of channels are updated.

.. image:: _static/flint/model/scan_model.png
    :alt: Scan model
    :align: center

.. image:: _static/flint/model/scan_model_group.png
    :alt: Scan model
    :align: center

Channels can be structured by groups. Scatter groups are described in a specific
structure to provide helpers. Channels can be reached by axis id, or channels
which are not part of axis (named counters).
"""

from __future__ import annotations
from typing import Optional
from typing import List
from typing import Iterator
from typing import Dict
from typing import Any
from typing import Set
from typing import NamedTuple

import logging
import numpy
import enum
import weakref

from silx.gui import qt


_logger = logging.getLogger(__name__)


class SealedError(Exception):
    """Exception occured when an object is sealed."""

    def __init__(self, message=None):
        if message is None:
            message = "The object is sealed, then not anymore editable."
        super(SealedError, self).__init__(message)


class _Sealable:
    """Abstract class for sealable object."""

    def __init__(self):
        self.__isSealed = False

    def seal(self):
        self.__isSealed = True

    def isSealed(self):
        return self.__isSealed


class ScanDataUpdateEvent:
    """Event containing the list of the updated channels.

    This event is shared by the `Scan` signal `scanDataUpdated`.
    """

    def __init__(
        self,
        scan: Scan,
        masterDevice: Optional[Device] = None,
        channel: Optional[Channel] = None,
        channels: Optional[List[Channel]] = None,
    ):
        """Event emitted when data from a scan is updated.

        `masterDevice` and `channel` can't be used both at the same time.

        Args:
            scan: The source scan of this event
            masterDevice: The root device from the acquisition chain tree which
                emit this event. In this case all the sub-channels have to be
                updated (except image and MCA channels, which always have specific
                event).
            channel: The channel source of this event
        """
        nb = sum([channel is not None, channels is not None, masterDevice is not None])
        if nb > 1:
            raise ValueError("Only a single attribute have to be set")
        self.__masterDevice = masterDevice
        self.__channel = channel
        self.__channels = channels
        self.__scan = scan
        self.__channelNames: Optional[Set[str]] = None

    def scan(self) -> Scan:
        return self.__scan

    def selectedDevice(self) -> Optional[Device]:
        return self.__masterDevice

    def selectedChannel(self) -> Optional[Channel]:
        return self.__channel

    def selectedChannels(self) -> Optional[List[Channel]]:
        return self.__channels

    def __eq__(self, other):
        if not isinstance(other, ScanDataUpdateEvent):
            return False
        return self.__channel is other.selectedChannel()

    def updatedChannelNames(self) -> Set[str]:
        if self.__channelNames is None:
            channelNames = {c.name() for c in self.iterUpdatedChannels()}
            self.__channelNames = channelNames
        return self.__channelNames

    def isUpdatedChannelName(self, channelName: str) -> bool:
        updatedChannels = self.updatedChannelNames()
        return channelName in updatedChannels

    def __iterUpdatedDevices(self):
        if self.__channel is not None:
            yield self.__channel.device()
            return
        for device in self.__scan.devices():
            if self.__masterDevice is not None:
                if device is not self.__masterDevice:
                    # FIXME: master() is not accurate. It could be a sub-master
                    if device.master() is not self.__masterDevice:
                        continue
            yield device

    def iterUpdatedChannels(self):
        if self.__channel is not None:
            yield self.__channel
            return
        if self.__channels is not None:
            for channel in self.__channels:
                yield channel
            return
        for device in self.__iterUpdatedDevices():
            for channel in device.channels():
                if channel.type() not in set([ChannelType.IMAGE, ChannelType.SPECTRUM]):
                    yield channel


class ScanState(enum.Enum):
    INITIALIZED = 0
    PROCESSING = 1
    FINISHED = 2


class Scan(qt.QObject, _Sealable):
    """Description of the scan object.

    A scan object contains all the informations generated by Redis about a scan.

    The data structure is fixed during a scan. Only channel data will be updated
    to be updated.

    It provides:

    - Signals for the life cycle of the scan (`scanStarted`, `scanDataUpdated`...)
    - A tree of `Device`, and `Channel` objects, plus helper to reach them.
    - The raw `scan_info`
    - Helper to cache information at the `Scan` level (which have a meaning
        during the scan life cycle)
    """

    scanStarted = qt.Signal()
    """Emitted when the scan acquisition starts"""

    scanSuccessed = qt.Signal()
    """Emitted when the scan acquisition succeeded."""

    scanFailed = qt.Signal()
    """Emitted when the scan acquisition failed."""

    scanFinished = qt.Signal()
    """Emitted when the scan acquisition finished.

    This signal is emitted after `scanFailed` or `scanFinished`.
    """

    scanDataUpdated = qt.Signal([], [ScanDataUpdateEvent])

    def __init__(self, parent=None):
        qt.QObject.__init__(self, parent=parent)
        _Sealable.__init__(self)
        self.__devices: List[Device] = []
        self.__channels: Dict[str, Channel] = {}
        self.__cacheData: Dict[Any, Any] = {}
        self.__cacheMessage: Dict[Any, Any] = {}
        self.__scanInfo = {}
        self.__finalScanInfo = None
        self.__state = ScanState.INITIALIZED
        self.__group = None
        self.__scatterData: List[ScatterData] = []

    def _setState(self, state: ScanState):
        """Private method to set the state of the scan."""
        self.__state = state

    def state(self) -> ScanState:
        """Returns the state of the scan."""
        return self.__state

    def seal(self):
        self.__channels = {}
        for device in self.__devices:
            device.seal()
            self.__cacheChannels(device)
        for scatterData in self.__scatterData:
            scatterData.seal()
        super(Scan, self).seal()

    def setGroup(self, group):
        self.__group = weakref.ref(group)

    def group(self):
        if self.__group is None:
            return None
        return self.__group()

    def setScanInfo(self, scanInfo: Dict):
        if self.isSealed():
            raise SealedError()
        # FIXME: It would be good to create a read-only recursive proxy to expose it
        self.__scanInfo = scanInfo

    def scanInfo(self) -> Dict:
        return self.__scanInfo

    def type(self) -> Optional[str]:
        """Returns the scan type stored in the scan info"""
        return self.__scanInfo.get("type", None)

    def hasPlotDescription(self) -> bool:
        """True if the scan contains plot description"""
        return len(self.__scanInfo.get("plots", [])) > 0

    def _setFinalScanInfo(self, scanInfo: Dict):
        self.__finalScanInfo = scanInfo

    def finalScanInfo(self) -> Optional[Dict]:
        return self.__finalScanInfo

    def addDevice(self, device: Device):
        if self.isSealed():
            raise SealedError()
        if device in self.__devices:
            raise ValueError("Already in the device list")
        self.__devices.append(device)

    def getDeviceByName(self, name: str) -> Device:
        elements = name.split(":")
        for device in self.__devices:
            current = device
            for e in reversed(elements):
                if current is None or current.name() != e:
                    break
                current = current.master()
            else:
                # The item was found
                if current is None:
                    return device

        raise ValueError("Device %s not found." % name)

    def _fireScanDataUpdated(
        self,
        channelName: str = None,
        masterDeviceName: str = None,
        channels: List[Channel] = None,
    ):
        self.__cacheData = {}
        # FIXME: Only clean up object relative to the edited channels
        self.__cacheMessage = {}

        if masterDeviceName is None and channelName is None and channels is None:
            # Propagate the event to all the channels of the this scan
            event = ScanDataUpdateEvent(self)
        elif masterDeviceName is not None:
            # Propagate the event to all the channels contained on this device (recursively)
            device = self.getDeviceByName(masterDeviceName)
            event = ScanDataUpdateEvent(self, masterDevice=device)
        elif channels is not None:
            # Propagate the event to many channels
            channel = self.getChannelByName(channelName)
            event = ScanDataUpdateEvent(self, channels=channels)
        elif channelName is not None:
            # Propagate the event to a single channel
            channel = self.getChannelByName(channelName)
            event = ScanDataUpdateEvent(self, channel=channel)
        else:
            assert False
        self.scanDataUpdated[ScanDataUpdateEvent].emit(event)
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

    def getChannelNames(self) -> List[str]:
        return list(self.__channels.keys())

    def addScatterData(self, scatterData: ScatterData):
        if self.isSealed():
            raise SealedError()
        self.__scatterData.append(scatterData)

    def getScatterDataByChannel(self, channel: Channel) -> Optional[ScatterData]:
        for data in self.__scatterData:
            if data.contains(channel):
                return data
        return None

    def hasCachedResult(self, obj: Any) -> bool:
        """True if the `obj` object have stored cache in this scan."""
        return obj in self.__cacheData

    def getCachedResult(self, obj: Any) -> Any:
        """Returns a cached data relative to `obj` else raise a `KeyError`."""
        return self.__cacheData[obj]

    def setCachedResult(self, obj: Any, result: Any):
        """Store a cache data relative to `obj`."""
        self.__cacheData[obj] = result

    def hasCacheValidation(self, obj: Any, version: int) -> bool:
        """
        Returns true if this version of the object was validated.
        """
        result = self.__cacheMessage.get(obj, None)
        if result is None:
            return False
        if result[0] != version:
            return False
        return True

    def setCacheValidation(self, obj: Any, version: int, result: Optional[str]):
        """
        Set the validation of a mutable object.

        This feature is used to store validation message relative to a scan time.
        When the scan data is updated, this cache have to be stored again.

        The implementation only store a validation for a single version of an
        object. This could change.
        """
        current = self.__cacheMessage.get(obj)
        if current is not None and current[0] == version:
            raise KeyError("Result already stored for this object version")
        self.__cacheMessage[obj] = (version, result)

    def getCacheValidation(self, obj: Any, version: int) -> Optional[str]:
        """
        Returns None if the object was validated, else returns a message
        """
        result = self.__cacheMessage[obj]
        if result[0] != version:
            raise KeyError("Version do not match")
        return result[1]


class ScanGroup(Scan):
    """Scan group object.

    It can be a normal scan but can contains extra scans.
    """

    subScanAdded = qt.Signal(object)
    """Emitted when a sub scan is added to this scan."""

    def __init__(self, parent=None):
        Scan.__init__(self, parent=parent)
        self.__subScans = []

    def addSubScan(self, scan: Scan):
        self.__subScans.append(scan)
        self.subScanAdded.emit(scan)

    def subScans(self) -> List[Scan]:
        return list(self.__subScans)


class DeviceType(enum.Enum):
    """Enumerate the kind of devices"""

    NONE = 0
    """Default type"""

    UNKNOWN = -1
    """Unknown value specified in the scan_info"""

    LIMA = 1
    """Lima device as specified by the scan_info"""

    MCA = 2
    """MCA device as specified by the scan_info"""

    VIRTUAL_ROI = 3
    """Device containing channel data from the same ROI.
    It is a GUI concept, there is no related device on the BLISS side.
    """


class DeviceMetadata(NamedTuple):
    info: Dict
    """raw metadata as stored by the scan_info"""

    roi: Optional[object]
    """Define a ROI geometry, is one"""


class Device(qt.QObject, _Sealable):
    """
    Description of a device.

    In the GUI side, a device is an named object which can contain other devices
    and channels. This could not exactly match the Bliss API.
    """

    _noneMetadata = DeviceMetadata({}, None)

    def __init__(self, parent: Scan):
        qt.QObject.__init__(self, parent=parent)
        _Sealable.__init__(self)
        self.__name: str = ""
        self.__metadata: DeviceMetadata = self._noneMetadata
        self.__type: DeviceType = DeviceType.NONE
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

    def fullName(self):
        """Path name from top master to this device.

        Each short name is separated by ":".
        """
        elements = [self.name()]
        parent = self.__master
        while parent is not None:
            elements.append(parent.name())
            parent = parent.__master
        return ":".join(reversed(elements))

    def setMetadata(self, metadata: DeviceMetadata):
        if self.isSealed():
            raise SealedError()
        self.__metadata = metadata

    def metadata(self) -> DeviceMetadata:
        """
        Returns a bunch of metadata stored within the channel.
        """
        return self.__metadata

    def addChannel(self, channel: Channel):
        if self.isSealed():
            raise SealedError()
        if channel in self.__channels:
            raise ValueError("Already in the channel list")
        self.__channels.append(channel)

    def channels(self) -> Iterator[Channel]:
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

    def isChildOf(self, master: Device) -> bool:
        """Returns true if this device is the child of `master` device."""
        parent = self.__master
        while parent is not None:
            if parent is master:
                return True
            parent = parent.__master
        return False

    def setType(self, deviceType: DeviceType):
        if self.isSealed():
            raise SealedError()
        self.__type = deviceType

    def type(self) -> DeviceType:
        """
        Returns the kind of this channel.
        """
        return self.__type


class ChannelType(enum.Enum):
    """Enumerate the kind of channels"""

    COUNTER = 0
    """Type of channel which store a single data per trigger.
    The sequence of acquisition is stored."""
    SPECTRUM = 1
    """Type of channel which store a list of data per trigger.
    Only the last data stored."""
    IMAGE = 2
    """Type of channel which store a 2d image per trigger.
    Only the last data stored."""


class AxisKind(enum.Enum):
    FORTH = "forth"
    BACKNFORTH = "backnforth"
    STEP = "step"

    # Deprecated code from user scripts from BLISS 1.4
    FAST = "fast"
    # Deprecated code from user scripts from BLISS 1.4
    FAST_BACKNFORTH = "fast-backnforth"
    # Deprecated code from user scripts from BLISS 1.4
    SLOW = "slow"
    # Deprecated code from user scripts from BLISS 1.4
    SLOW_BACKNFORTH = "slow-backnforth"


class ChannelMetadata(NamedTuple):
    start: Optional[float]
    stop: Optional[float]
    min: Optional[float]
    max: Optional[float]
    points: Optional[int]
    axisId: Optional[int]
    axisPoints: Optional[int]
    axisKind: Optional[AxisKind]
    group: Optional[str]
    axisPointsHint: Optional[int]
    dim: Optional[int]


class ScatterData(_Sealable):
    """Data structure of a scatter"""

    def __init__(self):
        super(ScatterData, self).__init__()
        self.__channels: List[List[Channel]] = []
        self.__noIndexes: List[Channel] = []
        self.__contains: Set[Channel] = set([])
        self.__values: List[Channel] = []

    def maxDim(self):
        return len(self.__channels)

    def channelsAt(self, axisId: int) -> List[Channel]:
        """Returns the list of channels stored at this axisId"""
        return self.__channels[axisId]

    def findGroupableAt(self, axisId: int) -> Optional[Channel]:
        """Returns a channel which can be grouped at a specific axisId"""
        for channel in self.channelsAt(axisId):
            if channel.metadata().axisKind == AxisKind.STEP:
                return channel
        return None

    def channelAxis(self, channel: Channel):
        for i in range(len(self.__channels)):
            if channel in self.__channels[i]:
                return i
        raise IndexError()

    def counterChannels(self):
        return list(self.__values)

    def addAxisChannel(self, channel: Channel, axisId: int):
        """Add channel as an axis of the scatter"""
        if self.isSealed():
            raise SealedError()
        if axisId is None:
            self.__noIndexes.append(channel)
        else:
            while len(self.__channels) <= axisId:
                self.__channels.append([])
            self.__channels[axisId].append(channel)
        self.__contains.add(channel)

    def addCounterChannel(self, channel: Channel):
        """Add channel used as a counter"""
        self.__values.append(channel)

    def contains(self, channel: Channel) -> bool:
        return channel in self.__contains

    def seal(self):
        for channel in self.__noIndexes:
            self.__channels.append([channel])
        del self.__noIndexes
        super(ScatterData, self).seal()

    def shape(self):
        """Returns the theorical ndim shape based on channels metadata.

        It is supported by numpy arrays. If a channel do not have `axisPoints`
        specified, -1 is used.
        """
        result = []
        for axisId in range(self.maxDim()):
            size = None
            for channel in self.__channels[axisId]:
                size = channel.metadata().axisPoints
                if size is not None:
                    break
            result.append(size)
        return tuple(reversed(result))


class Channel(qt.QObject, _Sealable):
    """
    Description of a channel.

    In the GUI side, a channel is leaf of the scan tree, which contain the raw
    data from Bliss through Redis.

    A channel have a specific data kind which can't change during the scan.
    It will only be feed with this kind of data.
    """

    dataUpdated = qt.Signal(object)
    """Emitted when setData is invoked.
    """

    _noneMetadata = ChannelMetadata(
        None, None, None, None, None, None, None, None, None, None, None
    )

    _dimToType = {0: ChannelType.COUNTER, 1: ChannelType.SPECTRUM, 2: ChannelType.IMAGE}

    def __init__(self, parent: Device):
        qt.QObject.__init__(self, parent=parent)
        _Sealable.__init__(self)
        self.__data: Optional[Data] = None
        self.__metadata: ChannelMetadata = self._noneMetadata
        self.__name: str = ""
        self.__type: ChannelType = None
        self.__displayName: Optional[str] = None
        self.__unit: Optional[str] = None
        self.__refreshRates: Dict[str, Optional[int]] = {}
        self.__updatedCount = 0
        parent.addChannel(self)

    def setType(self, channelType: ChannelType):
        if self.isSealed():
            raise SealedError()
        self.__type = channelType

    def type(self) -> ChannelType:
        """
        Returns the kind of this channel.

        FIXME this have to be property checked before remove (use device type instead or not)
        """
        if self.__type is None:
            return self._dimToType.get(self.__metadata.dim, ChannelType.COUNTER)
        return self.__type

    def setMetadata(self, metadata: ChannelMetadata):
        if self.isSealed():
            raise SealedError()
        self.__metadata = metadata

    def metadata(self) -> ChannelMetadata:
        """
        Returns a bunch of metadata stored within the channel.
        """
        return self.__metadata

    def setDisplayName(self, displayName: str):
        if self.isSealed():
            raise SealedError()
        self.__displayName = displayName

    def displayName(self) -> Optional[str]:
        """
        Returns the preferred display name of this channel.
        """
        return self.__displayName

    def setUnit(self, unit: str):
        if self.isSealed():
            raise SealedError()
        self.__unit = unit

    def unit(self) -> Optional[str]:
        """
        Returns the unit of this channel.
        """
        return self.__unit

    def device(self) -> Device:
        """
        Returns the device containing this channel.
        """
        return self.parent()

    def master(self) -> Device:
        """
        Returns the first master containing this channel.
        """
        parent = self.device()
        if parent.isMaster():
            return parent
        else:
            return parent.master()

    def name(self) -> str:
        """
        Returns the full name of the channel.

        It is a unique identifier during a scan.
        """
        return self.__name

    def baseName(self) -> str:
        """
        Returns the trail sequence of the channel name.
        """
        return self.__name.split(":")[-1]

    @property
    def ndim(self) -> int:
        """
        Returns the amount of dimensions of the data, before reaching the data.

        Mimics numpy arrays."""
        dim = self.__metadata.dim
        if dim is not None:
            if dim == 0:
                # scalar are stored with an extra "time/step" dimension
                return dim + 1
            return dim

        if self.__type == ChannelType.COUNTER:
            # one value per count
            return 1
        elif self.__type == ChannelType.SPECTRUM:
            # one value per MCA channel
            return 1
        elif self.__type == ChannelType.IMAGE:
            # FIXME; This have no meaning anymore as we support RGB and RGBA
            return 2
        else:
            assert False

    def setName(self, name: str):
        if self.isSealed():
            raise SealedError()
        self.__name = name

    def hasData(self) -> bool:
        """
        True if a data is set to this channel.

        A channel can contain nothing during a scan.
        """
        return self.__data is not None

    def data(self) -> Optional[Data]:
        """
        Returns the data associated to this channel.

        It is the only one attribute which can be updated during a scan.
        """
        return self.__data

    def array(self) -> Optional[numpy.array]:
        """
        Returns the array associated to this channel.

        This method is a shortcut to `.data().array()`.
        """
        if self.__data is None:
            return None
        return self.__data.array()

    def isDataCompatible(self, data: Data) -> bool:
        """
        True if this `data` is compatible with this channel.
        """
        if data is None:
            return True
        array = data.array()
        if array is None:
            return True
        if self.ndim == array.ndim:
            return True
        if self.__type == ChannelType.IMAGE:
            if array.ndim == 3:
                if array.shape[2] in [3, 4]:
                    return True
        return False

    def setData(self, data: Data):
        """
        Set the data associated to this channel.

        If the data is updated the signal `dataUpdated` is invoked.
        """
        if not self.isDataCompatible(data):
            raise ValueError("Data do not fit the channel requirements")
        if self.__data is data:
            return
        self.__updatedCount += 1
        self.__data = data
        self.dataUpdated.emit(data)

    def setPreferedRefreshRate(self, key: str, rate: Optional[int]):
        """Allow to specify the prefered refresh rate.

        It have to be specified in millisecond.
        """
        if rate is None:
            if key in self.__refreshRates:
                del self.__refreshRates[key]
        else:
            self.__refreshRates[key] = rate

    def preferedRefreshRate(self) -> Optional[int]:
        if len(self.__refreshRates) == 0:
            return None
        return min(self.__refreshRates.values())

    def updatedCount(self) -> int:
        """Amount of time the data was updated."""
        return self.__updatedCount


class Data(qt.QObject):
    """
    Store a `numpy.array` associated to a channel.

    This object was designed to be non-mutable in order to allow fast comparison,
    and to store metadata relative to the measurement (like unit, error) or
    helper to deal with the data (like hash). Could be renamed into `Quantity`.
    """

    def __init__(
        self,
        parent=None,
        array: numpy.ndarray = None,
        frameId: int = None,
        source: str = None,
        receivedTime: float = None,
    ):
        qt.QObject.__init__(self, parent=parent)
        self.__array = array
        self.__frameId = frameId
        self.__source = source
        self.__receivedTime = receivedTime

    def array(self) -> numpy.ndarray:
        return self.__array

    def frameId(self) -> int:
        """Frame number, only valid for images"""
        return self.__frameId

    def source(self) -> str:
        """Source of the image, only valid for images"""
        return self.__source

    def receivedTime(self) -> float:
        """Timestamp in second when the application received this data"""
        return self.__receivedTime
