# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

def __find_class(cfg_node):
    klass_name = cfg_node['class']

    if 'package' in cfg_node:
        module_name = cfg_node['package']
    elif 'module' in cfg_node:
        module_name = 'bliss.controllers.%s' % cfg_node['module']
    else:
        # discover module and class name
        module_name = 'bliss.controllers.%s' % klass_name.lower()

    module = __import__(module_name, fromlist=[None])
    klass = getattr(module, klass_name)

    return klass


def create_objects_from_config_node(config, item_cfg_node):
    klass = __find_class(item_cfg_node)

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
