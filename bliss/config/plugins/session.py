# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .utils import find_class

def create_objects_from_config_node(config, item_cfg_node):
    klass = find_class(item_cfg_node,'bliss.session')
    
    item_name = item_cfg_node["name"]
    
    return { item_name: klass(item_name, item_cfg_node) }
