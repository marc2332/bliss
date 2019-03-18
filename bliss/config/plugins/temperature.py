# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import logging
from bliss.common import log
from bliss.config.plugins.bliss import find_class


def create_objects_from_config_node(config, item_cfg_node):
    parent_node = item_cfg_node.parent
    item_name = item_cfg_node["name"]

    inputs = list()
    outputs = list()
    loops = list()
    names = dict()
    for category, objects in [
        ("inputs", inputs),
        ("outputs", outputs),
        ("ctrl_loops", loops),
    ]:
        pnode_cat = parent_node.get(category)
        if pnode_cat:
            for config_item in pnode_cat:
                name = config_item.get("name")
                objects.append((name, config_item))
                names.setdefault(category, list()).append(name)

    controller_class = find_class(parent_node, "bliss.controllers.temperature")
    controller = controller_class(parent_node, inputs, outputs, loops)

    cache_dict = dict()
    for category in ("inputs", "outputs", "ctrl_loops"):
        try:
            cache_dict.update(
                dict(zip(names[category], [controller] * len(names[category])))
            )
        except KeyError:
            pass

    # controller.initialize()
    o = controller.get_object(item_name)
    if item_name in dict(loops).keys():
        referenced_object = o.config["input"][1:]
        if referenced_object in controller._objects:
            # referencing an object in same controller
            o._Loop__input = controller._objects[referenced_object]
        else:
            o._Loop__input = config.get(referenced_object)
        referenced_object = o.config["output"][1:]
        if referenced_object in controller._objects:
            # referencing an object in same controller
            o._Loop__output = controller._objects[referenced_object]
        else:
            o._Loop__output = config.get(referenced_object)

    return {item_name: o}, cache_dict


def create_object_from_cache(config, name, controller):
    o = controller.get_object(name)
    return o
