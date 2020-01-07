"""Compatibility module for pytango."""

from bliss.common.proxy import Proxy
from enum import IntEnum
import functools

__all__ = [
    "AttrQuality",
    "EventType",
    "DevState",
    "AttributeProxy",
    "DeviceProxy",
    "ApiUtil",
]


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


class DevSource(IntEnum):
    DEV = 0
    CACHE = 1
    CACHE_DEV = 2


def _DeviceProxy(*args, **kwargs):
    raise RuntimeError(
        "Tango is not imported. Hint: is tango Python module installed ?"
    )


def _AttributeProxy(*args, **kwargs):
    raise RuntimeError(
        "Tango is not imported. Hint: is tango Python module installed ?"
    )


def Database(*args, **kwargs):
    raise RuntimeError(
        "Tango is not imported. Hint: is tango Python module installed ?"
    )


class _ApiUtil:
    def __getattribute__(self, attr):
        raise RuntimeError(
            "Tango is not imported. Hint: is tango Python module installed ?"
        )


ApiUtil = _ApiUtil()

try:
    from tango import (
        AttrQuality,
        EventType,
        DevState,
        DevFailed,
        Database,
        DevSource,
        ApiUtil,
    )
    from tango.gevent import (
        DeviceProxy as _DeviceProxy,
        AttributeProxy as _AttributeProxy,
    )
except ImportError:
    # PyTango < 9 imports
    try:
        from PyTango import (
            AttrQuality,
            EventType,
            DevState,
            DevFailed,
            Database,
            DevSource,
            ApiUtil,
        )
        from PyTango.gevent import (
            DeviceProxy as _DeviceProxy,
            AttributeProxy as _AttributeProxy,
        )
    except ImportError:
        pass


class DeviceProxy(Proxy):
    """A transparent wrapper of DeviceProxy, to make sure TANGO cache is not used by default"""

    def __init__(self, *args, **kwargs):
        super().__init__(
            functools.partial(_DeviceProxy, *args, **kwargs), init_once=True
        )
        self.set_source(DevSource.DEV)


class AttributeProxy(Proxy):
    """A transparent wrapper of AttributeProxy, to make sure TANGO cache is not used by default"""

    def __init__(self, *args, **kwargs):
        super().__init__(
            functools.partial(_AttributeProxy, *args, **kwargs), init_once=True
        )
        self.get_device_proxy().set_source(DevSource.DEV)


def get_fqn(proxy):
    """
    Returns the fully qualified name of a DeviceProxy or an AttributeProxy in the format
    `tango://<host>:<port>/<dev_name>[/<attr_name>]`
    """
    try:
        name = proxy.dev_name()
    except AttributeError:
        name = get_fqn(proxy.get_device_proxy())
        return "{}/{}".format(name, proxy.name())
    host = proxy.get_db_host()
    port = proxy.get_db_port()
    return "tango://{}:{}/{}".format(host, port, name)
