# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Scan meta is a way to add metadata for any scans.

Categories will be represent by groups underneath the scan
group except from POSITIONERS.
"""
__all__ = ["get_user_scan_meta"]

import copy as copy_module
import enum
import pprint
import weakref

from bliss import global_map
from bliss.common.protocols import HasMetadataForScan
from bliss.common.logtools import user_warning


class META_TIMING(enum.Flag):
    START = enum.auto()
    END = enum.auto()


USER_SCAN_META = None


def get_user_scan_meta():
    global USER_SCAN_META
    if USER_SCAN_META is None:
        USER_SCAN_META = ScanMeta()
        USER_SCAN_META.positioners.set("positioners", fill_positioners)
        USER_SCAN_META.positioners.timing = META_TIMING.START | META_TIMING.END
        USER_SCAN_META.instrument.set("@NX_class", {"@NX_class": "NXinstrument"})
        USER_SCAN_META.instrument.timing = META_TIMING.END
        USER_SCAN_META.technique.set("@NX_class", {"@NX_class": "NXcollection"})
    return USER_SCAN_META


class ScanMetaCategory:
    """Provides an API part of the metadata belonging to one category
    """

    def __init__(self, category, metadata, timing):
        """
        :param CATEGORIES category:
        :param dict metadata: CATEGORIES -> str or callable
        :param dict timing: CATEGORIES -> META_TIMING
        """
        self._category = category
        self._metadata = metadata
        self._timing = timing

    @property
    def category(self):
        return self._category

    @property
    def name(self):
        return self._category.name

    @property
    def metadata(self):
        return self._metadata.setdefault(self.category, dict())

    @property
    def timing(self):
        return self._timing.setdefault(self.category, META_TIMING.START)

    @timing.setter
    def timing(self, timing):
        self._timing[self.category] = timing

    def _parse_metadata_name(self, name_or_device):
        """
        :param name_or_device: string or an object with a name property
        :returns str or None:
        """
        if isinstance(name_or_device, str):
            if not name_or_device:
                user_warning("A name is required to publish scan metadata")
                return None
            return name_or_device
        else:
            try:
                name = name_or_device.name
                if name:
                    return name
            except AttributeError:
                pass
            user_warning(
                repr(name_or_device) + " needs a name to publish scan metadata"
            )
            return None

    def set(self, name_or_device, values):
        """
        :param name_or_device: string or an object with a name property
        :param callable or dict values: callable needs to return a dictionary
        """
        name = self._parse_metadata_name(name_or_device)
        if name:
            self.metadata[name] = values

    def is_set(self, name_or_device) -> bool:
        """
        :param name_or_device: string or an object with a name property
        :returns bool:
        """
        name = self._parse_metadata_name(name_or_device)
        return name in self.metadata

    def remove(self, name_or_device):
        """
        :param name_or_device: string or an object with a name property
        """
        name = self._parse_metadata_name(name_or_device)
        metadata = self.metadata
        metadata.pop(name, None)
        if not metadata:
            self._metadata.pop(self.category, None)

    @property
    def names(self):
        return list(self.metadata.keys())

    def __info__(self):
        s = pprint.pformat(self.metadata, indent=2)
        return f"{self.__class__.__name__}{self.name}: \n " + s


class ScanMeta:
    """Register metadata for all scans. The `Scan` object will call `ScanMeta.to_dict`
    to generate the metadata.

    To add static metadata for a particular scan you pass it to the scan as an argument:

        scan_info={"instrument": "mydetector":{"@NX_class": "NXdetector", "myparam": 1}}
        s = loopscan(..., scan_info={"instrument": "mydetector":{"myparam": 1}})
    """

    CATEGORIES = enum.Enum("categories", "INSTRUMENT POSITIONERS TECHNIQUE")

    def __init__(self, metadata=None, timing=None):
        if metadata is None:
            self._metadata = dict()
        else:
            self._metadata = metadata
        if timing is None:
            self._timing = dict()
        else:
            self._timing = timing

    @classmethod
    def categories_names(cls):
        return [cat.name.lower() for cat in cls.CATEGORIES]

    @classmethod
    def add_categories(cls, names):
        names = {s.upper() for s in names}
        original = {m.name for m in cls.CATEGORIES}
        new = original | names
        if original != new:
            cls.CATEGORIES = enum.Enum("categories", " ".join(new))

    @classmethod
    def remove_categories(cls, names):
        names = {s.upper() for s in names}
        original = {m.name for m in cls.CATEGORIES}
        new = original - names
        if original != new:
            cls.CATEGORIES = enum.Enum("categories", " ".join(new))

    def __getattr__(self, name):
        cat = self._scan_meta_category(name)
        if cat is None:
            raise AttributeError(name)
        else:
            return cat

    def _scan_meta_category(self, category):
        """
        :param CATEGORIES or str category:
        :returns ScanMetaCategory:
        """
        if isinstance(category, str):
            category = self.CATEGORIES.__members__.get(category.upper(), None)
        if category is None:
            return None
        else:
            return ScanMetaCategory(category, self._metadata, self._timing)

    def to_dict(self, scan, timing=META_TIMING.START):
        """Generate metadata
        """
        result = dict()
        for category, metadata in list(self._metadata.items()):
            smcategory = self._scan_meta_category(category)
            if smcategory is None:
                # Category was removed
                self._metadata.pop(category, None)
                continue
            if timing not in smcategory.timing:
                # Category metadata should not be generated at this time
                continue
            catname = category.name.lower()
            for name, values in smcategory.metadata.items():
                if callable(values):
                    try:
                        values = values(scan)
                    except Exception as e:
                        err_msg = f"Error in generating {repr(name)} metadata for user metadata category {repr(catname)}"
                        raise RuntimeError(err_msg) from e
                    if values is None:
                        continue
                cat_dict = result.setdefault(catname, dict())
                cat_dict.update(values)
        return result

    def clear(self):
        """Clear all metadata
        """
        self._metadata.clear()

    def _metadata_copy(self):
        mdcopy = dict()
        for category, metadata in list(self._metadata.items()):
            mdcat = mdcopy[category] = dict()
            for name, values in metadata.items():
                # A deep copy of an object method appears to copy
                # the object itself
                if not callable(values):
                    values = copy_module.deepcopy(values)
                mdcat[name] = values
        return mdcopy

    def copy(self):
        return self.__class__(
            metadata=self._metadata_copy(), timing=copy_module.copy(self._timing)
        )

    def used_categories_names(self):
        return [n.name.lower() for n in self._metadata.keys()]

    def __info__(self):
        s = pprint.pformat(self._metadata, indent=2)
        return f"{self.__class__.__name__}: \n " + s


def fill_positioners(scan):
    stuffix = "_start"
    if scan.state == 3:
        stuffix = "_end"
    positioners = dict()
    positioners_dial = dict()
    units = dict()
    for axis_name, axis_pos, axis_dial_pos, unit in global_map.get_axes_positions_iter(
        on_error="ERR"
    ):
        if axis_pos != "*DIS*":
            positioners[axis_name] = axis_pos
            positioners_dial[axis_name] = axis_dial_pos
            units[axis_name] = unit

    rd = {
        "positioners" + stuffix: positioners,
        "positioners_dial" + stuffix: positioners_dial,
    }

    if scan.state != 3:
        rd["positioners_units"] = units

    return rd
