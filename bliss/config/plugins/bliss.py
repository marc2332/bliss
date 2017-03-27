# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

import weakref

from .utils import find_class



def _checkref(config,item_cfg_node,referenced_objects,name,value):
    if isinstance(value, str) and value.startswith("$"):
        # convert reference to item from config
        obj = weakref.proxy(config.get(value))
        item_cfg_node[name]=obj
        referenced_objects[name]=obj
        return True
    else:
        return False

def _parse_dict(config,item_cfg_node,referenced_objects,
                subdict):
    for name,node in subdict.iteritems():
        if _checkref(config,item_cfg_node,referenced_objects,
                     name,node):
            continue
        elif isinstance(node,dict):
            childdict = dict()
            childref = dict()
            _parse_dict(config,childdict,childref,node)
            if childref:
                node.update(childref)
                referenced_objects[name] = node
            subdict.update(childdict)
        elif isinstance(node,list):
            return_list = _parse_list(config,node)
            if return_list:
                referenced_objects[name] = return_list
                item_cfg_node[name] = return_list

def _parse_list(config,value):
    object_list = list()
    for node in value:
        if isinstance(node,str) and node.startswith("$"):
            object_list.append(weakref.proxy(config.get(node)))
        elif isinstance(node,dict):
            subdict = dict()
            subref = dict()
            _parse_dict(config,subdict,subref,node)
            if subdict:
                node.update(subdict)
                object_list.append(node)
        elif isinstance(node,list):
            return_list = _parse_list(config,node)
            if return_list:
                object_list.append(return_list)
    return object_list

def create_objects_from_config_node(config, cfg_node):
    item_cfg_node = cfg_node.deep_copy()
    klass = find_class(item_cfg_node)

    item_name = item_cfg_node["name"]
    referenced_objects = dict()

    for name, value in item_cfg_node.iteritems():
        if _checkref(config,item_cfg_node,referenced_objects,
                           name,value):
            continue

        if isinstance(value,list):
            return_list = _parse_list(config,value)
            if return_list:
                referenced_objects[name] = return_list
                item_cfg_node[name] = return_list
        elif isinstance(value,dict):
            subdict = dict()
            subref = dict()
            _parse_dict(config,subdict,subref,value)
            if subref:
                referenced_objects[name] = subref
            item_cfg_node.update(subdict)

    o = klass(item_name, item_cfg_node)

    for name, object in referenced_objects.iteritems():
        if hasattr(o, name):
           continue
           #raise RuntimeError("'%s` member would be shadowed by reference in yml config file." % name)
        else:
            setattr(o, name, object) #add_property(o, name, object)

    return { item_name: o }
