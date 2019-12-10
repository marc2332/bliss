# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss session configuration utilities
"""

import os
import re
from bliss import current_session
from bliss.config import static


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


def current_scan_saving():
    """
    Get session's SCAN_SAVING object

    :returns bliss.scanning.scan.ScanSaving:
    """
    return current_session.scan_saving


def scan_saving_get(attr, default=None, scan_saving=None):
    """
    Get attribute from the session's scan saving object

    :param str attr:
    :param default:
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns str:
    """
    if scan_saving is None:
        scan_saving = current_scan_saving()
    return getattr(scan_saving, attr, default)


def scan_saving_attrs(template=None, scan_saving=None, **overwrite):
    """
    SCAN_SAVING attributes from template

    :param str template: SCAN_SAVING.template when missing
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :param overwrite: overwrite attribute values
    :returns str:
    """
    if scan_saving is None:
        scan_saving = current_scan_saving()
    if template is None:
        template = scan_saving.template
    params = {}
    for attr in re.findall(r"\{(.*?)\}", template):
        if attr in overwrite:
            params[attr] = overwrite[attr]
        else:
            try:
                params[attr] = getattr(scan_saving, attr)
            except AttributeError:
                pass
    return params


def beamline():
    """
    :returns str:
    """
    name = "id00"
    for k in "BEAMLINENAME", "BEAMLINE":
        name = os.environ.get(k, name)
    name = static_root().get("beamline", name)
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
