# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
