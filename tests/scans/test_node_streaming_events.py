# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import numpy
from bliss.config import streaming_events
from bliss.data import events


def test_channel_streaming_events():
    # Empty
    events.ChannelDataEvent([], {"dtype": None})

    # String content
    data = ["a", "b"]
    desc = {"shape": (1,), "dtype": str}
    ev = events.ChannelDataEvent(data, desc)
    assert all(data == ev.sequence)

    # Merge float events from stream
    data = numpy.asarray([1., 2])
    desc = {"shape": (2,), "dtype": float}
    ev1 = events.ChannelDataEvent(data, desc)
    data = [[1., 2, 3]]
    desc = {"shape": (3,), "dtype": float}
    ev2 = events.ChannelDataEvent(data, desc)
    data = [[1., 2, 3, 4], [1., 2, 3, 4]]
    desc = {"shape": (4,), "dtype": float}
    ev3 = events.ChannelDataEvent(data, desc)
    evts = [(1, ev1.encode()), (2, ev2.encode()), (3, ev3.encode())]
    ev = streaming_events.StreamEvent.merge_factory(evts)
    assert ev.description == {"shape": (4,), "dtype": float}
    assert ev.ndim == 1
    expected = [
        [1, 2, numpy.nan, numpy.nan],
        [1, 2, 3, numpy.nan],
        [1, 2, 3, 4],
        [1, 2, 3, 4],
    ]
    numpy.testing.assert_array_equal(ev.array, expected)
