# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import absolute_import

from .utils import find_class, replace_reference_by_object


def create_objects_from_config_node(config, cfg_node):
    item_cfg_node = cfg_node.deep_copy()
    klass = find_class(item_cfg_node)

    item_name = item_cfg_node["name"]
    referenced_objects = dict()

    replace_reference_by_object(config, item_cfg_node, referenced_objects)

    o = klass(item_name, item_cfg_node)

    for name, object in referenced_objects.iteritems():
        if hasattr(o, name):
            continue
            # raise RuntimeError("'%s` member would be shadowed by reference in yml config file." % name)
        else:
            setattr(o, name, object)  # add_property(o, name, object)

    return {item_name: o}
