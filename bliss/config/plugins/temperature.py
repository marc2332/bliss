# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import itertools
from bliss.common.temperature import Input, Output, Loop
from bliss.config.plugins.utils import find_class, replace_reference_by_object


def create_objects_from_config_node(config, node):
    if "inputs" in node or "outputs" in node or "loops" in node:
        # asking for a controller
        obj_name = None
    else:
        obj_name = node.get("name")
        node = node.parent

    controller_class_name = node.get("class")
    controller_name = node.get("name")
    controller_class = find_class(node, "bliss.controllers.temperature")
    controller_module = sys.modules[controller_class.__module__]

    inputs = dict()
    outputs = dict()
    loops = dict()
    node = node.to_dict()
    cache_dict = dict()

    for (objects, default_class, config_nodes_list) in (
        (inputs, Input, node.get("inputs", [])),
        (outputs, Output, node.get("outputs", [])),
        (loops, Loop, node.get("ctrl_loops", [])),
    ):
        for config_dict in config_nodes_list:
            config_dict = config_dict.copy()
            object_name = config_dict.get("name")
            if object_name.startswith("$"):
                object_class = None
                object_name = object_name.strip("$")
            else:
                cache_dict[object_name] = config_dict
                object_class_name = config_dict.get("class")
                if object_class_name is None:
                    try:
                        object_class_name = default_class.__name__
                        object_class = getattr(controller_module, object_class_name)
                    except AttributeError:
                        object_class = default_class
                else:
                    object_class = getattr(controller_module, object_class_name)
            objects[object_name] = (object_class, config_dict)

    controller = controller_class(node, inputs, outputs, loops)
    cache_dict = {
        name: (controller, config_dict) for name, config_dict in cache_dict.items()
    }
    objects_dict = {}
    if controller_name:
        objects_dict[controller_name] = controller
    yield objects_dict, cache_dict

    controller._init()

    if obj_name is not None:
        obj = config.get(obj_name)
        yield {obj_name: obj}


def create_object_from_cache(config, name, cache_objects):
    controller, config_dict = cache_objects
    replace_reference_by_object(config, config_dict)
    return controller.get_object(name)
