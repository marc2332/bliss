# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss.config import streaming_events


def test_streaming_events_derive():
    # The bare minimal custom event (no extra data)
    class MyStreamEvent(streaming_events.StreamEvent):
        TYPE = b"MYTYPE"

    assert MyStreamEvent().encode() == {b"__EVENT__": b"MYTYPE"}

    # Missing event type

    with pytest.raises(NotImplementedError):

        class WrongStreamEvent1(streaming_events.StreamEvent):
            pass

    # Wrong event type

    with pytest.raises(NotImplementedError):

        class WrongStreamEvent2(streaming_events.StreamEvent):
            TYPE = "WRONGTYPE"


def test_streaming_events_init():
    # Create event based on stream data: up-casting allowed
    ev1 = streaming_events.EndEvent()
    raw = ev1.encode()
    classes = [
        streaming_events.StreamEvent,
        streaming_events.TimeEvent,
        streaming_events.EndEvent,
    ]
    types = [ev1.types.UNKNOWN, ev1.types.time, ev1.types.end]
    for cls, evtype in zip(classes, types):
        assert cls.istype(raw)
        assert cls.isstricttype(raw) == (cls is ev1.__class__)
        ev2 = cls(raw=raw)
        assert isinstance(ev2, cls)
        assert ev2.TYPE == evtype
        ev2 = cls.factory(raw=raw)
        assert isinstance(ev2, streaming_events.EndEvent)
        assert ev2.TYPE == ev2.types.END
        assert ev1.time == ev2.time

    # Create event based on stream data: down-casting not allowed
    ev1 = streaming_events.StreamEvent()
    raw = ev1.encode()
    classes = [streaming_events.TimeEvent, streaming_events.EndEvent]
    for cls in classes:
        assert not cls.istype(raw)
        assert cls.isstricttype(raw) == (cls is ev1.__class__)
        with pytest.raises(streaming_events.StreamDecodeError):
            ev2 = cls(raw=raw)
        with pytest.raises(streaming_events.StreamDecodeError):
            ev2 = cls.factory(raw=raw)

    # Create event based on unknown stream data
    lst = [{"random_data": None}, {b"__EVENT__": b"__WRONG__"}]
    for raw in lst:
        ev2 = streaming_events.StreamEvent(raw=raw)
        assert isinstance(ev2, streaming_events.StreamEvent)
        # Does not allow down-casting
        with pytest.raises(streaming_events.StreamDecodeError):
            ev2 = streaming_events.EndEvent(raw=raw)


def test_streaming_events_encoding():
    ev1 = streaming_events.EndEvent()

    # Encode/decode roundtrip
    raw = ev1.encode()
    ev1.decode(raw)

    # Decode data with wrong structure
    with pytest.raises(streaming_events.StreamDecodeError):
        ev1.decode({"random_data": None})

    # Encode corrupted event
    with pytest.raises(streaming_events.StreamEncodeError):
        ev1.time = None
        ev1.encode()


def test_streaming_generic_encoding():
    def assert_roundtrip(data):
        errmsg = f"Encoding/decoding error for {repr(data)}"
        encode, decode = streaming_events.StreamEvent.encode_decode_methods(type(data))
        try:
            data2 = decode(encode(data))
        except Exception as e:
            raise RuntimeError(errmsg) from e
        assert type(data) is type(data2), errmsg
        if isinstance(data, numpy.ndarray):
            assert all(data == data2), errmsg
        else:
            assert data == data2, errmsg

    lst = [
        b"123",
        "123",
        123,
        123.,
        [1, 2, 3],
        {1, 2, 3},
        (1, 2, 3),
        {1: 1, 2: 2, 3: 3},
        numpy.array([1, 2, 3]),
    ]
    for data in lst:
        assert_roundtrip(data)
