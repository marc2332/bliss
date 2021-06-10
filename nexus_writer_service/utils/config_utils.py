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
Static Bliss configuration utilities
"""

import os
from bliss.config import static


def static_config():
    """
    :returns bliss.config.static.Config:
    """
    return static.get_config()


def static_root(root=None):
    """
    :returns ConfigNode:
    """
    if root is None:
        return static_config().root
    else:
        return root


def static_root_find(name, root=None):
    """
    :returns ConfigNode:
    """
    root = static_root(root=root)
    if root.children:
        for node in root.children:
            if node.get("name", None) == name:
                return node
    nodes = []
    for node in root.values():
        if isinstance(node, static.ConfigNode):
            nodes.append(node)
        elif isinstance(node, list):
            for nodei in node:
                if isinstance(nodei, static.ConfigNode):
                    nodes.append(nodei)
    for node in nodes:
        if node.get("name", None) == name:
            return node
        ret = static_root_find(name, root=node)
        if ret is not None:
            return ret
    return None


def beamline(root=None, default="id00"):
    """
    :returns str:
    """
    name = default
    for k in "BEAMLINENAME", "BEAMLINE":
        name = os.environ.get(k, name)
    root = static_root(root=root)
    name = root.get("beamline", name)
    scan_saving = static_root_find("scan_saving", root=root)
    if scan_saving is not None:
        name = scan_saving.get("beamline", name)
    return name.lower()


def institute(root=None, default=""):
    """
    :returns str:
    """
    root = static_root(root=root)
    name = default
    name = root.get("institute", name)
    name = root.get("laboratory", name)
    name = root.get("synchrotron", name)
    return name


def instrument(root=None, default=""):
    """
    :returns str:
    """
    root = static_root(root=root)
    name = institute(root=root, default=default)
    name = root.get("instrument", name)
    return name
