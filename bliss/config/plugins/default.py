# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from .utils import replace_reference_by_object


def create_objects_from_config_node(config, item_cfg_node):
    item_name = item_cfg_node["name"]

    replace_reference_by_object(config, item_cfg_node)

    return {item_name: item_cfg_node}
