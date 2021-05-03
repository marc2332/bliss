# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.config.plugins.utils import find_top_class_and_node
from bliss.controllers.bliss_controller import BlissController


def create_objects_from_config_node(cfg_obj, cfg_node):

    """
        Create an object from the config with a given name (unique). 
        It ensures that the controller and sub-objects are only created once.
        
        This function resolves dependencies between the BlissController and its sub-objects with a name.
        It looks for the 'class' key in 'cfg_node' (or at upper levels) to instantiate the BlissController.
        All sub-configs of named sub-objects owned by the controller are stored as cached items for later instantiation via config.get.

        args:
            cfg_obj: a Config object (from config.static)
            cfg_node: a ConfigNode object (from config.static)

        yield: 
            tuple: (created_items, cached_items)
    """

    # search the 'class' key in cfg_node or at a upper node level
    # then return the class and the associated config node
    klass, ctrl_node = find_top_class_and_node(cfg_node)
    ctrl_name = ctrl_node.get("name")  # ctrl could have a name in config
    item_name = cfg_node["name"]  # name of the item that should be created and returned

    # always create the bliss controller first
    bctrl = klass(ctrl_node)

    # print(f"\n=== From config: {item_name} from {bctrl.name}")

    if isinstance(bctrl, BlissController):

        # prepare subitems configs and cache item's controller.
        # the controller decides which items should be cached and which controller
        # is associated to the cached item (in case the cached item is owned by a sub-controller of this controller)
        cacheditemnames2ctrl = bctrl._prepare_subitems_configs()
        # print(f"\n=== Caching: {list(cacheditemnames2ctrl.keys())} from {bctrl.name}")

        # --- add the controller to registered items, if it has a name.
        name2items = {}
        if ctrl_name:
            name2items[ctrl_name] = bctrl

        # update the config cache dict now to avoid cyclic instanciation with internal references
        # an internal reference occurs when a subitem config uses a reference to another subitem owned by the same controller.
        yield name2items, cacheditemnames2ctrl

        # load config and init controller
        bctrl._controller_init()

        # --- don't forget to instanciate the object for which this function has been called (if not a controller)
        if item_name != ctrl_name:
            obj = cfg_obj.get(item_name)
            yield {item_name: obj}

        # --- Now any new object_name going through 'config.get( obj_name )' should call 'create_object_from_cache' only.
        # --- 'create_objects_from_config_node' should never be called again for any object related to the controller instanciated here (see config.get code)

    elif (
        item_name == ctrl_name
    ):  # allow instantiation of top object which is not a BlissController
        yield {ctrl_name: bctrl}
        return
    else:  # prevent instantiation of an item comming from a top controller which is not a BlissController
        raise TypeError(f"{bctrl} is not a BlissController object!")


def create_object_from_cache(config, name, bctrl):
    # print(f"\n=== From cache: {name} from {bctrl.name}")
    return bctrl._get_subitem(name)
