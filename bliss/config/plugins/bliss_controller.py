# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from re import subn
from bliss.config.plugins.utils import find_class_and_node

# from bliss.config.static import ConfigNode, ConfigReference


def find_sub_names_config(
    config, selection=None, level=0, parent_key=None, exclude_ref=True
):
    """ Search in a config the sub-sections where the key 'name' is found. 
        
        Returns a dict of tuples (sub_config, parent_key) indexed by level (0 is the top level).
        
        sub_config: a sub-config containing 'name' key
        parent_key: key under which the sub_config was found (None for level 0)
        exclude_ref: if True, exclude sub-config with name as reference ($)
    """

    if selection is None:
        selection = {}

    if selection.get(level) is None:
        selection[level] = []

    if config.get("name"):
        if not exclude_ref or not config.get("name").startswith("$"):
            selection[level].append((config, parent_key))

    for k, v in config.items():
        if isinstance(v, dict):
            find_sub_names_config(v, selection, level + 1, k)

        elif isinstance(v, list):
            for i in v:
                if isinstance(i, dict):
                    find_sub_names_config(i, selection, level + 1, k)

    return selection


def create_objects_from_config_node(cfg_obj, cfg_node):

    """
        Create an object from the config with a given name (unique). 
        It ensures that the controller and sub-objects are only created once.
        
        This function resolves dependencies between the BlissController and its sub-objects with a name.
        It looks for the 'class' key in 'cfg_node' (or at upper levels) to instantiate the BlissController.
        All sub-configs of named sub-objects are stored as cached items for later instantiation via config.get.

        args:
            cfg_obj: a Config object (from config.static)
            cfg_node: a ConfigNode object (from config.static)

        yield: 
            tuple: ( created_items, cached_items)
    """

    print("\n===== BLISS CONTROLLER PLUGIN  FROM CONFIG: ", cfg_node["name"])

    name2items = {}
    name2cacheditems = {}

    # search the 'class' key in cfg_node or at a upper node level
    # return the class and the associated config node
    klass, ctrl_node = find_class_and_node(cfg_node)
    # print("=== FOUND BLISS CONTROLLER CLASS", klass, "WITH NODE", ctrl_node)

    ctrl_name = ctrl_node.get("name")
    item_name = cfg_node["name"]  # name of the item that should be created and returned

    # always create the bliss controller first
    bctrl = klass(ctrl_name, ctrl_node.clone())

    # find all sub objects with a name in controller config
    sub_cfgs = find_sub_names_config(ctrl_node.to_dict())
    for level in sorted(sub_cfgs.keys()):
        if level != 0:  # ignore the controller itself
            for cfg, pkey in sub_cfgs[level]:
                subname = cfg["name"]
                if subname == item_name:  # this is the sub-object to return
                    name2items[item_name] = bctrl._create_sub_item(item_name, cfg, pkey)
                else:  # store sub-object info for later instantiation
                    name2cacheditems[subname] = (bctrl, cfg, pkey)

    # --- add the controller to stored items if it has a name
    if ctrl_name:
        name2items[ctrl_name] = bctrl

    # update the config cache dict NOW to avoid cyclic instanciation (i.e. config.get => create_object_from_... => config.get )
    yield name2items, name2cacheditems

    # --- NOW, any new object_name going through 'config.get( obj_name )' should call 'create_object_from_cache' only.
    # --- 'create_objects_from_config_node' should never be called again for any object related to the controller instanciated here (see config.get code)


def create_object_from_cache(config, name, cached_object_info):
    print("===== REGULATION FROM CACHE", name)  # config,  name, object_info)
    bctrl, cfg, pkey = cached_object_info
    return bctrl._create_sub_item(name, cfg, pkey)
