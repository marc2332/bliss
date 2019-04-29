# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


from .utils import find_class_and_node, replace_reference_by_object


def create_objects_from_config_node(config, cfg_node):
    item_cfg_node = cfg_node.deep_copy()
    klass, node = find_class_and_node(item_cfg_node)

    item_name = item_cfg_node["name"]
    referenced_objects = dict()

    replace_reference_by_object(config, node, referenced_objects)

    o = klass(item_name, item_cfg_node)

    for name, object in referenced_objects.items():
        if hasattr(o, name):
            continue
            # raise RuntimeError("'%s` member would be shadowed by reference in yml config file." % name)
        else:
            setattr(o, name, object)  # add_property(o, name, object)

    return {item_name: o}
