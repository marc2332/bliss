# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import itertools
from bliss.common.temperature import Input, Output, Loop
from bliss.config.plugins.utils import find_class, replace_reference


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

    inputs, inputs_names = [], []
    outputs, outputs_names = [], []
    loops, loops_names = [], []
    node = node.to_dict()

    for (
        objects,
        objects_names,
        default_class,
        default_class_name,
        config_nodes_list,
    ) in (
        (inputs, inputs_names, Input, "", node.get("inputs", [])),
        (outputs, outputs_names, Output, "", node.get("outputs", [])),
        (loops, loops_names, Loop, "", node.get("ctrl_loops", [])),
    ):
        for config_dict in config_nodes_list:
            replace_reference(config, config_dict)
            if not isinstance(config_dict.get("name"), str):
                # reference
                object_class = config_dict.get("name")
                object_name = object_class.name
            else:
                object_name = config_dict.get("name")
                object_class_name = config_dict.get("class")
                if object_class_name is None:
                    try:
                        object_class_name = default_class.__name__
                        object_class = getattr(controller_module, object_class_name)
                    except AttributeError:
                        object_class = default_class
                else:
                    object_class = getattr(controller_module, object_class_name)
            objects_names.append(object_name)
            objects.append((object_name, object_class, config_dict))

    controller = controller_class(node, inputs, outputs, loops)

    controller._init()

    all_names = inputs_names + outputs_names + loops_names
    cache_dict = dict(zip(all_names, [controller] * len(all_names)))
    objects_dict = {}
    if controller_name:
        objects_dict[controller_name] = controller
    if obj_name is not None:
        obj = controller.get_object(obj_name)
        objects_dict[obj_name] = obj
    return objects_dict, cache_dict


def create_object_from_cache(config, name, controller):
    o = controller.get_object(name)
    return o
