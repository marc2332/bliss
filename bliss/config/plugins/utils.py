# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
from importlib.util import find_spec


def camel_case_to_snake_style(name):
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def find_class(cfg_node, base_path="bliss.controllers"):
    return find_class_and_node(cfg_node, base_path)[0]


def find_class_and_node(cfg_node, base_path="bliss.controllers"):
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

    try:
        module = __import__(module_name, fromlist=[""])
    except ModuleNotFoundError as e:
        if find_spec(module_name) is not None:
            raise e
        module_name = "%s.%s" % (base_path, camel_case_to_snake_style(klass_name))
        try:
            module = __import__(module_name, fromlist=[""])

        except ModuleNotFoundError as e2:
            if find_spec(module_name) is not None:
                raise e2
            else:
                msg = "CONFIG COULD NOT FIND CLASS!"
                msg += "\nWITH CONFIG  MODULE NAME: " + e.msg
                msg += "\nWITH DEFAULT MODULE NAME: " + e2.msg
                msg += f"\nCHECK THAT MODULE NAME BEGINS AFTER '{base_path}'\n"
                raise ModuleNotFoundError(msg)

    try:
        klass = getattr(module, klass_name)
    except AttributeError:
        klass = getattr(module, klass_name.title())

    return klass, node


def _checkref(config, item_cfg_node, referenced_objects, name, value, placeholder):
    if isinstance(value, str) and value.startswith("$"):
        # convert reference to item from config
        value = value.lstrip("$")
        if placeholder:
            obj = placeholder(value)
        else:
            obj = config.get(value)
        item_cfg_node[name] = obj
        referenced_objects[name] = obj
        return True
    else:
        return False


def _parse_dict(config, item_cfg_node, referenced_objects, subdict, placeholder):
    for name, value in tuple(subdict.items()):
        if _checkref(config, subdict, referenced_objects, name, value, placeholder):
            continue
        elif isinstance(value, dict):
            childdict = dict()
            childref = dict()
            _parse_dict(config, childdict, childref, value, placeholder)
            if childref:
                value.update(childref)
                referenced_objects[name] = value
            subdict.update(childdict)
        elif isinstance(value, list):
            return_list = _parse_list(config, value, placeholder)
            if return_list:
                referenced_objects[name] = return_list
                item_cfg_node[name] = return_list


def _parse_list(config, value, placeholder):
    object_list = list()
    for node in value:
        if isinstance(node, str) and node.startswith("$"):
            node = node.lstrip("$")
            if placeholder:
                object_list.append(placeholder(node))
            else:
                object_list.append(config.get(node))
        elif isinstance(node, dict):
            subdict = dict()
            subref = dict()
            _parse_dict(config, subdict, subref, node, placeholder)
            if subdict:
                node.update(subdict)
                object_list.append(node)
        elif isinstance(node, list):
            return_list = _parse_list(config, node, placeholder)
            if return_list:
                object_list.append(return_list)
        else:
            object_list.append(node)
    return object_list


def replace_reference_by_object(
    config, item_cfg_node, ref_objects=None, placeholder=None
):
    referenced_objects = ref_objects if ref_objects is not None else dict()
    for name, value in tuple(item_cfg_node.items()):
        if _checkref(
            config, item_cfg_node, referenced_objects, name, value, placeholder
        ):
            continue

        if isinstance(value, list):
            return_list = _parse_list(config, value, placeholder)
            if return_list:
                referenced_objects[name] = return_list
                item_cfg_node[name] = return_list
        elif isinstance(value, dict):
            subdict = dict()
            subref = dict()
            _parse_dict(config, subdict, subref, value, placeholder)
            if subref:
                referenced_objects[name] = subref
            item_cfg_node.update(subdict)
