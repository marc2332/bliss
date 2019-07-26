# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from .utils import find_class_and_node, replace_reference_by_object


def _find_name_in_list(l, name):
    for item in l:
        if isinstance(item, dict):
            find_node = _find_name_in_node(item, name)
            if find_node is not None:
                return find_node
        elif isinstance(item, list):
            find_node = _find_name_in_list(item, name)
            if find_node is not None:
                return find_node


def _find_name_in_node(node, name):
    for key, value in node.items():
        if key == "name" and value == name:
            return node
        if isinstance(value, dict):
            find_node = _find_name_in_node(value, name)
            if find_node is not None:
                return find_node
        elif isinstance(value, list):
            find_node = _find_name_in_list(value, name)
            if find_node is not None:
                return find_node


def create_objects_from_config_node(config, cfg_node):
    klass, node = find_class_and_node(cfg_node)
    node = node.deep_copy()

    item_name = cfg_node["name"]
    referenced_objects = dict()

    if node.get("name") != item_name:
        cfg_node = _find_name_in_node(node, item_name)
        assert cfg_node is not None
    else:
        cfg_node = node

    replace_reference_by_object(config, node, referenced_objects)

    o = klass(item_name, cfg_node)

    for name, object in referenced_objects.items():
        if hasattr(o, name):
            continue
            # raise RuntimeError("'%s` member would be shadowed by reference in yml config file." % name)
        else:
            setattr(o, name, object)  # add_property(o, name, object)

    return {item_name: o}
