# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import enum
import itertools
import weakref
from bliss.common.regulation import Input, Output, Loop
from bliss.config.plugins.utils import find_class, replace_reference_by_object


TYPE = enum.Enum("TYPE", "INPUT OUTPUT LOOP")

DEFAULT_CLASS_NAME = {TYPE.INPUT: "Input", TYPE.OUTPUT: "Output", TYPE.LOOP: "Loop"}

DEFAULT_CLASS = {TYPE.INPUT: Input, TYPE.OUTPUT: Output, TYPE.LOOP: Loop}


def create_objects_from_config_node(config, node):

    # print("CREATE OBJECT FROM CONFIG", node.get('name'))
    # --- for a better understanding of this function, see bliss.config.static => config.get( obj_name )

    if "inputs" in node or "outputs" in node or "ctrl_loops" in node:
        # --- dealing with a controller
        obj_name = None

    else:
        # --- dealing with a child of a controller (Input, Output, Loop) or something else using regulation plugin
        obj_name = node.get("name")
        node = node.parent  # <= step-up to controller node

    # --- whatever the object kind, first of all we instanciate the controller
    controller_name = node.get("name")  # usually is None
    controller_class = find_class(node, "bliss.controllers.temperature")
    controller = controller_class(node)
    controller.initialize()

    # --- prepare dictionaries for cached object and instanciated objects
    name2cacheditems = {}
    name2items = {}

    # --- store in cache the sub-objects of the controller for a later instanciation
    # --- for each type of a controller sub-node (i.e. inputs, outputs, loops)
    for node_type, child_nodes in (
        (TYPE.INPUT, node.get("inputs", [])),
        (TYPE.OUTPUT, node.get("outputs", [])),
        (TYPE.LOOP, node.get("ctrl_loops", [])),
    ):

        # --- for each subnode of a given type, store info in cache
        # name2cacheditems.update( { nd['name'] : (node_type, nd.deep_copy(), controller) for nd in child_nodes }  )

        for nd in child_nodes:
            # name = nd["name"]
            # if name.startswith(
            #     "$"
            # ):  # --- handle custom inputs/outputs which are given with a name as a reference (i.e. $name)
            #     new_obj = config.get(name)  # --- instanciate custom object now
            #     name2items[
            #         name
            #     ] = new_obj  # --- register in instanciated object dict of the config
            #     new_obj._controller = controller  # --- define the associated controller
            #     controller.register_object(
            #         new_obj
            #     )  # --- register the custom device in the controller
            # else:  # --- store in cache devices which are not custom
            name2cacheditems[nd["name"]] = (node_type, nd.deep_copy(), controller)

    # --- add the controller to stored items if it has a name
    if controller_name:
        name2items[controller_name] = controller

    # update the config cache dict NOW to avoid cyclic instanciation (i.e. config.get => create_object_from_... => replace_reference_by_object => config.get )
    yield name2items, name2cacheditems

    # --- don't forget to instanciate the object for which this function has been called
    # --- if it isn't a controller
    if obj_name is not None:
        obj = config.get(obj_name)
        yield {obj_name: obj}

    # --- NOW, any new object_name going through 'config.get( obj_name )' should call 'create_object_from_cache' only.
    # --- 'create_objects_from_config_node' should never be called again for any object related to the controller instanciated here (see config.get code)


def create_object_from_cache(config, name, object_info):

    # for a better understanding of this function, see bliss.config.static => config.get( obj_name )

    # print(f"===== CREATE FROM CACHE: {name}")
    node_type, node, controller = object_info
    replace_reference_by_object(config, node)

    controller_module = sys.modules[controller.__module__]
    object_class_name = node.get("class", DEFAULT_CLASS_NAME[node_type])

    try:
        object_class = getattr(controller_module, object_class_name)
    except AttributeError:
        object_class = DEFAULT_CLASS[node_type]

    new_object = controller.create_object(node_type.name, object_class, node)
    return new_object
