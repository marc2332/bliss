"""Compatibility module for pytango."""

from __future__ import absolute_import

from enum import IntEnum

__all__ = ['AttrQuality', 'EventType', 'DevState',
           'AttributeProxy', 'DeviceProxy']


class AttrQuality(IntEnum):
    ATTR_VALID = 0
    ATTR_INVALID = 1
    ATTR_ALARM = 2
    ATTR_CHANGING = 3
    ATTR_WARNING = 4


class EventType(IntEnum):
    CHANGE_EVENT = 0
    QUALITY_EVENT = 1
    PERIODIC_EVENT = 2
    ARCHIVE_EVENT = 3
    USER_EVENT = 4
    ATTR_CONF_EVENT = 5
    DATA_READY_EVENT = 6
    INTERFACE_CHANGE_EVENT = 7
    PIPE_EVENT = 8


class DevState(IntEnum):
    ON = 0
    OFF = 1
    CLOSE = 2
    OPEN = 3
    INSERT = 4
    EXTRACT = 5
    MOVING = 6
    STANDBY = 7
    FAULT = 8
    INIT = 9
    RUNNING = 10
    ALARM = 11
    DISABLE = 12
    UNKNOWN = 13


def DeviceProxy(*args, **kwargs):
    raise RuntimeError(
        "Tango is not imported. Hint: is tango Python module installed ?")


def AttributeProxy(*args, **kwargs):
    raise RuntimeError(
        "Tango is not imported. Hint: is tango Python module installed ?")


try:
    from tango import AttrQuality, EventType, DevState
    from tango.gevent import DeviceProxy, AttributeProxy
except ImportError:
    # PyTango < 9 imports
    try:
        from PyTango import AttrQuality, EventType, DevState
        from PyTango.gevent import DeviceProxy, AttributeProxy
    except ImportError:
        pass
