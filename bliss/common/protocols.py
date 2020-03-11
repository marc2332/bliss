# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
This file groups all protocols managed by bliss
"""
from collections import namedtuple
from typing_extensions import Protocol, runtime_checkable
from types import SimpleNamespace


class IterableNamespace(SimpleNamespace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __getitem__(self, key):
        try:
            return self.__dict__.__getitem__(key)
        except KeyError:
            return list(self.__dict__.values())[key]

    @property
    def _fields(self):
        return self.__dict__.keys()


def counter_namespace(counters):
    if isinstance(counters, dict):
        dct = counters
    elif isinstance(counters, IterableNamespace):
        return counters
    else:
        dct = {counter.name: counter for counter in counters}
    return IterableNamespace(**dct)
    # return namedtuple("namespace", dct)(**dct)


@runtime_checkable
class CounterContainer(Protocol):
    """
    Device that contains counters.
    """

    @property
    def counters(self) -> IterableNamespace:
        """
        Return a **counter_namespace** which hold a list of counters
        attached to this device.
        """
        raise NotImplementedError


@runtime_checkable
class Scannable(Protocol):
    """
    Any device that has this interface can be used
    in a step by step scan.
    """

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def position(self) -> float:
        """
        Return the current position
        """
        raise NotImplementedError

    @property
    def state(self):
        """
        Return the current state.
        """
        raise NotImplementedError

    def move(self, target_position):
        """
        This should 
        """
        raise NotImplementedError
