# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss session configuration utilities
"""

import os
import re
from functools import wraps
from bliss import current_session
from bliss.config import static
from bliss.scanning.scan_saving import ScanSaving, with_eval_dict


def static_config():
    """
    Get static session configuration

    :returns bliss.config.static.Config:
    """
    return static.get_config()


def static_root():
    """
    Get static session configuration

    :returns bliss.config.static.Node:
    """
    return static_config().root


def static_root_get(name, default=None):
    """
    Get attribute from the static session configuration

    :returns str:
    """
    return static_root().get(name, default)


def static_root_find(name, default=None, parent=None):
    """
    :param bliss.config.static.Node parent:
    :returns dict:
    """
    if parent is None:
        parent = static_root()
    if parent.children:
        for node in parent.children:
            if node.get("name", None) == name:
                return node.to_dict()
    nodes = []
    for node in parent.values():
        if isinstance(node, static.Node):
            nodes.append(node)
        elif isinstance(node, list):
            for nodei in node:
                if isinstance(nodei, static.Node):
                    nodes.append(nodei)
    for node in nodes:
        if node.get("name", None) == name:
            return node.to_dict()
        ret = static_root_find(name, parent=node)
        if ret:
            return ret
    return {}


def with_scan_saving(func):
    """Pass the current session's SCAN_SAVING instance as a named argument

    :param callable func:
    :returns callable:
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        scan_saving = kwargs.get("scan_saving")
        if scan_saving is None:
            kwargs["scan_saving"] = ScanSaving(current_session.name)
        return func(*args, **kwargs)

    return wrapper


@with_scan_saving
def scan_saving_get(attr, default=None, scan_saving=None):
    """
    Get attribute from the session's scan saving object

    :param str attr:
    :param default:
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns str:
    """
    return getattr(scan_saving, attr, default)


@with_eval_dict
@with_scan_saving
def scan_saving_eval(template, scan_saving=None, eval_dict=None):
    """
    Evaluate template with SCAN_SAVING attributes and properties.

    :param str template:
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :param dict eval_dict:
    :returns str:
    """
    return scan_saving.eval_template(template, eval_dict=eval_dict)


def beamline():
    """
    :returns str:
    """
    name = "id00"
    for k in "BEAMLINENAME", "BEAMLINE":
        name = os.environ.get(k, name)
    name = static_root_get("beamline", name)
    scan_saving = static_root_get("scan_saving", {})
    name = scan_saving.get("beamline", name)
    return name.lower()


def institute():
    """
    :returns str:
    """
    root = static_root()
    name = ""
    name = root.get("institute", name)
    name = root.get("laboratory", name)
    name = root.get("synchrotron", name)
    return name
