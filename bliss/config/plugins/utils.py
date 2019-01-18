# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


def find_class(cfg_node, base_path="bliss.controllers"):
    klass_name, node = cfg_node.get_inherited_value_and_node("class")
    if klass_name is None:
        raise KeyError("class")

    if "package" in node:
        module_name = node["package"]
    elif "module" in node:
        module_name = "%s.%s" % (base_path, node["module"])
    else:
        # discover module and class name
        module_name = "%s.%s" % (base_path, klass_name.lower())

    module = __import__(module_name, fromlist=[""])
    try:
        klass = getattr(module, klass_name)
    except AttributeError:
        klass = getattr(module, klass_name.title())

    return klass


def _checkref(config, item_cfg_node, referenced_objects, name, value):
    if isinstance(value, str) and value.startswith("$"):
        # convert reference to item from config
        obj = config.get(value)
        item_cfg_node[name] = obj
        referenced_objects[name] = obj
        return True
    else:
        return False


def _parse_dict(config, item_cfg_node, referenced_objects, subdict):
    for name, node in subdict.iteritems():
        if _checkref(config, subdict, referenced_objects, name, node):
            continue
        elif isinstance(node, dict):
            childdict = dict()
            childref = dict()
            _parse_dict(config, childdict, childref, node)
            if childref:
                node.update(childref)
                referenced_objects[name] = node
            subdict.update(childdict)
        elif isinstance(node, list):
            return_list = _parse_list(config, node)
            if return_list:
                referenced_objects[name] = return_list
                item_cfg_node[name] = return_list


def _parse_list(config, value):
    object_list = list()
    for node in value:
        if isinstance(node, (str, unicode)) and node.startswith("$"):
            object_list.append(config.get(node))
        elif isinstance(node, dict):
            subdict = dict()
            subref = dict()
            _parse_dict(config, subdict, subref, node)
            if subdict:
                node.update(subdict)
                object_list.append(node)
        elif isinstance(node, list):
            return_list = _parse_list(config, node)
            if return_list:
                object_list.append(return_list)
        else:
            object_list.append(node)
    return object_list


def replace_reference_by_object(config, item_cfg_node, ref_objects=None):
    referenced_objects = ref_objects if ref_objects is not None else dict()
    for name, value in item_cfg_node.iteritems():
        if _checkref(config, item_cfg_node, referenced_objects, name, value):
            continue

        if isinstance(value, list):
            return_list = _parse_list(config, value)
            if return_list:
                referenced_objects[name] = return_list
                item_cfg_node[name] = return_list
        elif isinstance(value, dict):
            subdict = dict()
            subref = dict()
            _parse_dict(config, subdict, subref, value)
            if subref:
                referenced_objects[name] = subref
            item_cfg_node.update(subdict)
