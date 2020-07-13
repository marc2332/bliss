# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Events that are added or read from a Redis stream have
a stream ID and carry a payload of type `dict`. The keys
and values need to be of type `bytes`.

To encode a custom data type to a raw stream payload
(and decode again when reading) a class can to be derived
from `StreamEvent`

    class MyStreamEvent(StreamEvent):
        TYPE = b"MYTYPE"

        def init(self, var1, var2=None):
            ...

        def _encode(self):
            raw = super()._encode()
            ... # add var1 and var2 to raw
            return raw

        def _decode(self, raw):
            super()._decode(raw)
            ... # get var1 and var2 from raw

To prepare data to be added to a Redis stream:

    event = MyStreamEvent(var1, var2=...)
    raw = event.encode()

The data of a Redis stream can be decoded as follows:

    event = StreamEvent.factory(raw)

The factory method allows up-casting:

    event = MyStreamEvent(var1, var2=...)
    event = StreamEvent.factory(event.encode())
    assert isinstance(event, MyStreamEvent)

If you don't want up-casting (avoid unnecessary decoding):

    event = MyStreamEvent(raw={...})

Down-casting raises an exception (missing data):

    event = StreamEvent()
    try:
        event = MyStreamEvent.factory(event.encode())
    except StreamDecodeError:
        ...

To know whether data from a Redis stream is of a
particular type without decoding it:

    if MyStreamEvent.istype(raw):
        ...

To know whether an event is of a particular type

    if event.TYPE == event.types.MYTYPE:
        ...

    if isinstance(event, MyStreamEvent):
        ...
"""

import pickle
import datetime
import numbers
import functools


class StreamError(Exception):
    pass


class StreamEncodeError(StreamError):
    pass


class StreamDecodeError(StreamError):
    pass


class StreamEventMeta(type):
    """Checks whether StreamEvent is being derived properly.
    Makes sure the class gets up-casted upon instantiation
    with data from a DataStream.
    """

    def __new__(self, name, bases, attr):
        """Register class when defined
        """
        cls = super().__new__(self, name, bases, attr)
        if hasattr(cls, "_SUBCLASS_REGISTRY"):
            # Register the subclass
            event_type = cls.TYPE
            ecls = cls._SUBCLASS_REGISTRY.get(event_type)
            if ecls is not None:
                raise NotImplementedError(
                    f"Event type {event_type} is already taken by class {ecls.__name__}"
                )
            if not isinstance(event_type, bytes):
                raise NotImplementedError("{cls.__name__}.TYPE must be of type 'bytes'")
            cls._SUBCLASS_REGISTRY[event_type] = cls
        else:
            # Register the base class
            cls._SUBCLASS_REGISTRY = {None: cls, cls.TYPE: cls}
        return cls


class _EventTypes:
    def __getattr__(self, attr):
        attr = attr.upper().encode()
        if attr in StreamEvent._SUBCLASS_REGISTRY:
            return attr
        raise AttributeError(attr)


class StreamEvent(metaclass=StreamEventMeta):
    """Base class to encode/decode DataStream events.
    """

    TYPE = b"UNKNOWN"
    TYPE_KEY = b"__EVENT__"
    types = _EventTypes()

    @classmethod
    def _use_class(cls, raw):
        event_type = raw.get(cls.TYPE_KEY, b"")
        try:
            # Get the proper class for this event type
            return cls._SUBCLASS_REGISTRY[event_type]
        except KeyError:
            # Event type is missing or unknown:
            # use the base class
            return cls._SUBCLASS_REGISTRY[None]

    @classmethod
    def istype(cls, raw):
        usecls = cls._use_class(raw)
        # issubclass does no work?
        # return issubclass(cls, usecls)
        return cls in usecls.__mro__

    @classmethod
    def isstricttype(cls, raw):
        return raw.get(cls.TYPE_KEY, b"") == cls.TYPE

    @classmethod
    def class_factory(cls, raw):
        """Returns the class StreamEvent or one of the derived
        classes, depending of the event type.

        :param dict raw: DataStream event data
        :raises StreamDecodeError:
        :returns type:
        """
        usecls = cls._use_class(raw)
        # issubclass does not work???
        # if not issubclass(cls, usecls):
        if cls not in usecls.__mro__:
            # Do not allow down-casting (up-casting is allowed)
            raise StreamDecodeError(f"Event not of type {cls.TYPE}")
        return usecls

    @classmethod
    def factory(cls, raw):
        """The returned object is on instance of
        this class or a derived classes, depending
        of the event type.

        :param dict raw: DataStream event data
        :raises StreamDecodeError:
        :returns StreamEvent:
        """
        usecls = cls.class_factory(raw=raw)
        return usecls(raw=raw)

    @classmethod
    def merge_factory(cls, events):
        """
        :param list((index, raw)) events:
        :returns StreamEvent:
        """
        if not events:
            return
        usecls = cls.class_factory(events[0][1])
        return usecls.merge(events)

    def __init__(self, *args, raw=None, **kw):
        if raw is None:
            self.init(*args, **kw)
        else:
            self.decode(raw)

    def __str__(self):
        return f"{self.__class__.__name__}({self.TYPE})"

    def init(self):
        pass

    def encode(self):
        """
        :raises StreamEncodeError:
        :returns dict: DataStream event data
        """
        try:
            return self._encode()
        except Exception as e:
            raise StreamEncodeError from e

    def decode(self, raw):
        """
        :param dict raw: DataStream event data
        :raises StreamDecodeError:
        """
        try:
            self._decode(raw)
        except Exception as e:
            raise StreamDecodeError from e

    def _encode(self):
        return {self.TYPE_KEY: self.TYPE}

    def _decode(self, raw):
        if not self.istype(raw):
            raise TypeError(f"Event not of type {self.TYPE}")

    @staticmethod
    def generic_encode(data, **kw):
        """
        :param Any data:
        :returns bytes:
        """
        return pickle.dumps(data, **kw)

    @staticmethod
    def generic_decode(data, **kw):
        """
        :param Any data:
        :returns Any:
        """
        return pickle.loads(data, **kw)

    @classmethod
    def encode_bytes(cls, data):
        return data

    @classmethod
    def decode_bytes(cls, data):
        return data

    @classmethod
    def encode_string(cls, data):
        return data.encode()

    @classmethod
    def decode_string(cls, data):
        return data.decode()

    @classmethod
    def encode_integral(cls, data):
        return b"%d" % data

    @classmethod
    def decode_integral(cls, data, int_type=int):
        return int_type(data.decode())

    @classmethod
    def encode_decode_methods(cls, data_type):
        if issubclass(data_type, bytes):
            return cls.encode_bytes, cls.decode_bytes
        elif issubclass(data_type, str):
            return cls.encode_string, cls.decode_string
        elif issubclass(data_type, numbers.Integral):
            decode = functools.partial(cls.decode_integral, int_type=data_type)
            return cls.encode_integral, decode
        else:
            return cls.generic_encode, cls.generic_decode

    @classmethod
    def merge(cls, events):
        """
        :param list((index, raw)) events:
        :returns StreamEvent:
        """
        raise NotImplementedError


class TimeEvent(StreamEvent):

    TYPE = b"TIME"
    TIMESTAMP_KEY = b"__TIMESTAMP__"
    STRTIME_KEY = b"__STRTIME__"

    STRTIME_FMT = "%a %b %d %H:%M:%S %Y"

    def init(self):
        self.time = datetime.datetime.now()

    @property
    def timestamp(self):
        return self.time.timestamp()

    @timestamp.setter
    def timestamp(self, epoch):
        self.time = datetime.datetime.fromtimestamp(float(epoch))

    @property
    def strftime(self):
        return self.time.strftime(self.STRTIME_FMT)

    def _encode(self):
        raw = super()._encode()
        raw[self.TIMESTAMP_KEY] = self.generic_encode(self.timestamp)
        raw[self.STRTIME_KEY] = self.encode_string(self.strftime)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.timestamp = self.generic_decode(raw[self.TIMESTAMP_KEY])


class StartEvent(TimeEvent):

    TYPE = b"START"


class EndEvent(TimeEvent):

    TYPE = b"END"
    EXCEPTION_KEY = b"__EXCEPTION__"

    def init(self, exception=None, **kw):
        super().init(**kw)
        self.exception = exception

    def _encode(self):
        raw = super()._encode()
        raw[self.EXCEPTION_KEY] = self.generic_encode(self.exception)
        return raw

    def _decode(self, raw):
        super()._decode(raw)
        self.exception = self.generic_decode(raw[self.EXCEPTION_KEY])
