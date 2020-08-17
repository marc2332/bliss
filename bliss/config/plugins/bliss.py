# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from bliss.config.plugins.utils import find_class_and_node
from bliss.config.static import ConfigNode, ConfigReference


def create_objects_from_config_node(config, cfg_node):
    klass, node = find_class_and_node(cfg_node)
    item_name = cfg_node["name"]

    if node.get("name") != item_name:
        cfg_node = ConfigNode.indexed_nodes[item_name]
    else:
        cfg_node = node

    o = klass(item_name, cfg_node.clone())

    for key, value in cfg_node.items():
        if isinstance(value, ConfigReference):
            if hasattr(o, key):
                continue
            else:
                setattr(o, key, value.dereference())

    return {item_name: o}
