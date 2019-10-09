# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides a storage for raw data coming from live scans.
"""
from __future__ import annotations
from typing import Optional
from typing import List
from typing import Dict
from typing import Tuple

import numpy


class DataStorage:
    def __init__(self):
        self.__data: Dict[str, numpy.ndarray] = {}
        self.__group: Dict[str, List[str]] = {}
        self.__groups: Dict[str, str] = {}

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

    def get_data(self, channel_name) -> numpy.ndarray:
        return self.__data[channel_name]

    def get_avaible_data_size(self, group_name: str) -> int:
        """Returns the minimal avaible size for all of the channels from a
        group."""
        size = None
        for channel_name in self.__group[group_name]:
            if channel_name in self.__data:
                data = self.get_data(channel_name)
                data_size = len(data)
            else:
                # This channel is not yet there
                # Then it's the smaller one
                return 0
            if size is None:
                size = data_size
            elif data_size < size:
                size = len(data)
        assert size is not None
        return size

    def set_data(self, channel_name: str, data: numpy.ndarray):
        self.__data[channel_name] = data

    def groups(self) -> List[str]:
        return list(self.__group.keys())

    def get_group(self, channel_name: str) -> str:
        return self.__groups[channel_name]

    def get_channels_by_group(self, group_name: str) -> List[str]:
        return self.__group[group_name]
