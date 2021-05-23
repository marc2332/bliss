# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
This file groups all protocols managed by bliss
"""
from abc import ABC
from collections import namedtuple
from types import SimpleNamespace
from typing import Mapping
from typing import Union


class IterableNamespace(SimpleNamespace):
    """Access to this namespace is compatible with named_tuple"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __getitem__(self, key):
        """works for both keys of dict or integer values of key"""
        try:
            return self.__dict__.__getitem__(key)
        except KeyError:
            return list(self.__dict__.values())[key]

    @property
    def _fields(self):
        """as for named tuple"""
        return self.__dict__.keys()

    def __add__(self, other):
        if isinstance(other, IterableNamespace):
            return IterableNamespace(**{**self.__dict__, **other.__dict__})
        elif isinstance(other, Mapping):
            return IterableNamespace(**{**self.__dict__, **other})
        else:
            raise TypeError

    def __info__(self):
        names = "".join(["." + x + "\n" for x in self.__dict__.keys()])
        return "Namespace containing:\n" + names

    def __len__(self):
        return len(self.__dict__)


def counter_namespace(counters):
    if isinstance(counters, dict):
        dct = counters
    elif isinstance(counters, IterableNamespace):
        return counters
    else:
        dct = {counter.name: counter for counter in counters}
    return IterableNamespace(**dct)
    # return namedtuple("namespace", dct)(**dct)


class CounterContainer(ABC):
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


class Scannable(ABC):
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
        This should move to target_position
        """
        raise NotImplementedError


class HasMetadataForDataset(ABC):
    """
    Any controller which provides metadata intended to be saved
    during a dataset life cycle.

    The `dataset_metadata` is called by the Bliss session's icat_mapping
    object when the session has such a mapping configured.
    """

    def dataset_metadata(self) -> Union[dict, None]:
        """
        Returning an empty dictionary means the controller has metadata
        but no values. `None` means the controller has no metadata.
        """
        raise NotImplementedError


class HasMetadataForScan(ABC):
    """
    Any controller which provides metadata intended to be saved
    during a scan life cycle.

    The `scan_metadata` method is called by the acquisition chain
    objects `AcquisitionObject` (directly or indirectly).
    """

    def disable_scan_metadata(self):
        self.__disabled_scan_metadata = True

    @property
    def scan_metadata_enabled(self):
        try:
            return not self.__disabled_scan_metadata
        except AttributeError:
            return True

    def enable_scan_metadata(self):
        self.__disabled_scan_metadata = False

    def scan_metadata(self) -> Union[dict, None]:
        """
        Returning an empty dictionary means the controller has metadata
        but no values. `None` means the controller has no metadata.
        """
        raise NotImplementedError

    @property
    def scan_metadata_name(self) -> Union[str, None]:
        """
        Default implementation returns self.name, can be overwritten in derived classes
        Returns None when there is no name
        """
        try:
            return self.name
        except AttributeError:
            return None

    @property
    def strict_scan_metadata(self):
        """
        Return whether metadata has to be reported only if the controller is involved in the scan
        """
        return False
