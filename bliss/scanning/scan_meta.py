# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Scan meta is a way to add metadata for any scans.
Information are classify into categories like:
 - instrument
 - sample
 - proposal
 - technique
 - ...
"""
__all__ = ["get_user_scan_meta"]

import copy as copy_module
import enum

from bliss import global_map

USER_SCAN_META = None
CATEGORIES = enum.Enum("categories", "INSTRUMENT POSITIONERS NEXUSWRITER TECHNIQUE")


class META_TIMING(enum.Flag):
    START = enum.auto()
    END = enum.auto()


def categories_names():
    return [cat.name.lower() for cat in CATEGORIES]


def get_user_scan_meta():
    global USER_SCAN_META
    if USER_SCAN_META is None:
        USER_SCAN_META = scan_meta()
        USER_SCAN_META.positioners.set("positioners", fill_positioners)
        USER_SCAN_META.positioners.timing = META_TIMING.START | META_TIMING.END
        USER_SCAN_META.instrument.set("@NX_class", {"@NX_class": "NXinstrument"})
        USER_SCAN_META.instrument.timing = META_TIMING.END
        USER_SCAN_META.technique.set("@NX_class", {"@NX_class": "NXcollection"})
    return USER_SCAN_META


def scan_meta(info=None, meta_timing=None):

    _infos = dict() if info is None else info
    _meta_timing = dict() if meta_timing is None else meta_timing

    class Category:
        def __init__(self, cat):
            self._cat = cat
            _meta_timing.setdefault(self._cat, META_TIMING.START)

        @property
        def timing(self):
            return _meta_timing[self._cat]

        @timing.setter
        def timing(self, timing):
            _meta_timing[self._cat] = timing

        def set(self, name_or_device, values):
            """
            set metadata information to scans.

            :param name_or_device is the access name must be unique or a device
            with a name property
            :param values is a dictionary or a callable which returns
            a  dictionary
            """
            name = (
                name_or_device
                if isinstance(name_or_device, str)
                else name_or_device.name
            )
            categories_info = _infos.setdefault(self._cat, dict())
            categories_info[name] = values

        def remove(self, name_or_device):
            name = (
                name_or_device
                if isinstance(name_or_device, str)
                else name_or_device.name
            )
            categories_infos = _infos.get(self._cat, dict())
            categories_infos.pop(name, None)
            if not categories_infos:
                _infos.pop(self._cat, None)

        @property
        def names(self):
            return list(_infos.get(self._cat, dict()).keys())

    def make_prop(cat):
        return property(lambda x: Category(cat))

    attrs = {cat.name.lower(): make_prop(cat) for cat in CATEGORIES}

    def to_dict(self, scan, timing=META_TIMING.START):
        rd = dict()
        for category, infos in _infos.items():
            if (
                timing in getattr(self, category.name.lower()).timing
            ):  # how to do this nicer?
                for name, values in infos.items():
                    try:
                        if callable(values):
                            values = values(scan)
                            if values is None:
                                continue
                        cat_dict = rd.setdefault(category.name.lower(), dict())
                        cat_dict.update(values)
                    except Exception as e:
                        err_msg = f"Invalid field {repr(name)} in category {repr(category.name)} of user scan metadata ({str(e)})"
                        raise RuntimeError(err_msg) from e
        return rd

    attrs["to_dict"] = to_dict

    def clear(self):
        """
        remove all info
        """
        _infos.clear()

    attrs["clear"] = clear

    def copy(self):
        return scan_meta(copy_module.deepcopy(_infos), _meta_timing)
        # TODO: does this really need to be a deepcopy?
        # there is a pretty weired thing e.g. in mulitposition
        # when one replaces
        # scan_meta_obj.instrument.set(self, lambda _:self.metadata_dict())
        # with
        # scan_meta_obj.instrument.set(self, self.metadata_dict)

    attrs["copy"] = copy

    def cat_list(self):
        return [n.name.lower() for n in _infos.keys()]

    attrs["cat_list"] = cat_list

    def __info__(self):
        return f"ScanMeta {_infos}"

    attrs["__info__"] = __info__

    klass = type("ScanMeta", (object,), attrs)
    return klass()


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
