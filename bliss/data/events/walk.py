# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Events returned received when walking a `DataNode`,
derived from raw Redis stream events.
"""

from typing import NamedTuple, Union, Sequence
from enum import Enum


__all__ = ["EventType", "EventData", "Event"]


class EventType(Enum):
    NEW_NODE = 1
    NEW_DATA = 2
    END_SCAN = 3
    PREPARED_SCAN = 4


class EventData(NamedTuple):
    first_index: int = -1
    """Index of the first element of `data`"""
    data: Union[None, Sequence, str] = None
    """Sequence of data points"""
    description: any = None
    """Data description from the raw DataStream events"""
    block_size: int = 0
    """Number of data points in this event"""


class Event(NamedTuple):
    type: EventType
    node: any
    """Node object that provides an API to the corresponding Redis node"""
    data: EventData = None
