# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
from importlib.util import find_spec


_ALIAS_TO_MODULE_NAME = {"Lima": "bliss.controllers.lima.lima_base"}
"""Alias defined for default BLISS controllers"""


def camel_case_to_snake_style(name):
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def find_class(cfg_node, base_path="bliss.controllers"):
    return find_class_and_node(cfg_node, base_path)[0]


def resolve_module_name(class_name, node, base_path):
    if "package" in node:
        result = node["package"]
    elif "module" in node:
        module_name = node["module"]
        result = "%s.%s" % (base_path, module_name)
    elif base_path == "bliss.controllers" and class_name in _ALIAS_TO_MODULE_NAME:
        # For BLISS base class, there is alias to the right module
        # In order to allow to move them without changing the configuration
        result = _ALIAS_TO_MODULE_NAME.get(class_name)
    else:
        # discover module and class name
        result = "%s.%s" % (base_path, class_name.lower())
    return result


def find_class_and_node(cfg_node, base_path="bliss.controllers"):
    class_name, node = cfg_node.get_inherited_value_and_node("class")
    if class_name is None:
        raise KeyError("class")
    module_name = resolve_module_name(class_name, node, base_path)
    try:
        module = __import__(module_name, fromlist=[""])
    except ModuleNotFoundError as e:
        if find_spec(module_name) is not None:
            raise e
        module_name = "%s.%s" % (base_path, camel_case_to_snake_style(class_name))
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
        klass = getattr(module, class_name)
    except AttributeError:
        klass = getattr(module, class_name.title())

    return klass, node
