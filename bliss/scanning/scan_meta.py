# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2019 Beamline Control Unit, ESRF
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

import enum

USER_SCAN_META = None


def get_user_scan_meta():
    global USER_SCAN_META
    if USER_SCAN_META is None:
        USER_SCAN_META = scan_meta()
    return USER_SCAN_META


def scan_meta():
    CATEGORIES = enum.Enum(
        "categories", "INSTRUMENT SAMPLE SAMPLE_DESCRIPTION PROPOSAL TECHNIQUE"
    )

    _infos = dict()

    class Category:
        def __init__(self, cat):
            self._cat = cat

        def set(self, name, values):
            """
            set metadata information to scans.

            :param name is the access name must be unique
            :param values is a dictionary or a callable which returns
            a  dictionary
            """
            categories_info = _infos.setdefault(self._cat, dict())
            categories_info[name] = values

        def remove(self, name):
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

    def to_dict(self, scan):
        rd = dict()
        for category, infos in _infos.items():
            for name, values in infos.items():
                if callable(values):
                    values = values(scan)
                cat_dict = rd.setdefault(category.name.lower(), dict())
                cat_dict.update(values)
        return rd

    attrs["to_dict"] = to_dict

    def clear(self):
        """
        remove all info
        """
        _infos.clear()

    attrs["clear"] = clear

    klass = type("ScanMeta", (object,), attrs)
    return klass()
