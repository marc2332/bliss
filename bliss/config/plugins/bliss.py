# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

from .utils import find_class

def create_objects_from_config_node(config, item_cfg_node):
    klass = find_class(item_cfg_node)

    item_name = item_cfg_node["name"]
    referenced_objects = dict()
    item_cfg_node_2_clean = set()

    for name, value in item_cfg_node.iteritems():
        if isinstance(value, str) and value.startswith("$"):
            # convert reference to item from config
            obj = config.get(value)
            item_cfg_node[name]=obj
            item_cfg_node_2_clean.add(name)
            referenced_objects[name]=item_cfg_node[name]
        elif isinstance(value,list):
            object_list = dict()
            for node in value:
                node_name = node.get('name','')
                if(isinstance(node,dict) and
                   node_name.startswith('$')):
                    ref_obj = config.get(node_name)
                    item_cfg_node[node_name] = ref_obj
                    object_list[node_name] = ref_obj
                    item_cfg_node_2_clean.add(node_name)
            if object_list:
                referenced_objects[name] = object_list

    o = klass(item_name, item_cfg_node)

    for name in item_cfg_node_2_clean:
        item_cfg_node.pop(name)

    for name, object in referenced_objects.iteritems():
        if hasattr(o, name):
           continue
           #raise RuntimeError("'%s` member would be shadowed by reference in yml config file." % name)
        else:
            setattr(o, name, object) #add_property(o, name, object)

    return { item_name: o }
