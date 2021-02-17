# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides a storage for raw data coming from live scans.
"""
from __future__ import annotations
from typing import Optional
from typing import List
from typing import Dict

import numpy
import logging


_logger = logging.getLogger(__name__)


class DataStorage:
    def __init__(self):
        self.__data: Dict[str, numpy.ndarray] = {}
        self.__group: Dict[str, List[str]] = {}
        self.__groups: Dict[str, str] = {}
        self.__last_size_per_group: Dict[str, int] = {}

    def clear(self):
        self.__data.clear()
        self.__group.clear()

    def create_channel(self, channel_name: str, group_name: str):
        if group_name in self.__group:
            self.__group[group_name].append(channel_name)
        else:
            self.__group[group_name] = [channel_name]
        self.__groups[channel_name] = group_name

    def has_channel(self, channel_name) -> bool:
        return channel_name in self.__groups

    def get_data_else_none(self, channel_name) -> Optional[numpy.ndarray]:
        return self.__data.get(channel_name, None)

    def get_data(self, channel_name) -> numpy.ndarray:
        return self.__data[channel_name]

    def get_last_group_size(self, group_name: str) -> int:
        """Returns the last stored group size."""
        return self.__last_size_per_group.get(group_name, 0)

    def update_group_size(self, group_name: str) -> Optional[int]:
        """Update the minimal available size for all of the channels.

        If this size was update, the new size is returned, else None is returned
        """
        size = None
        for channel_name in self.__group[group_name]:
            if channel_name in self.__data:
                data = self.get_data(channel_name)
                data_size = len(data)
            else:
                # This channel is not yet there
                # Then it's the smaller one
                return None
            if size is None:
                size = data_size
            elif data_size < size:
                size = len(data)
        assert size is not None
        if self.get_last_group_size(group_name) == size:
            return None
        self.__last_size_per_group[group_name] = size
        return size

    def append_data(self, channel_name: str, data: numpy.ndarray):
        # NOTE: We could avoid reallocation by allocating bigger arrays and use
        # memory view. But this was not speeding up anything for tested use cases
        prev_data = self.__data.get(channel_name, [])
        data = numpy.concatenate((prev_data, data))
        self.__data[channel_name] = data

    def set_data(self, channel_name: str, data: numpy.ndarray):
        self.__data[channel_name] = data

    def groups(self) -> List[str]:
        return list(self.__group.keys())

    def get_group(self, channel_name: str) -> str:
        return self.__groups[channel_name]

    def get_channels_by_group(self, group_name: str) -> List[str]:
        return self.__group[group_name]
