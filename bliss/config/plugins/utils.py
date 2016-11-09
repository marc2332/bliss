# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

def find_class(cfg_node,base_path='bliss.controllers'):
    klass_name = cfg_node['class']

    if 'package' in cfg_node:
        module_name = cfg_node['package']
    elif 'module' in cfg_node:
        module_name = '%s.%s' % (base_path,cfg_node['module'])
    else:
        # discover module and class name
        module_name = '%s.%s' % (base_path,klass_name.lower())

    module = __import__(module_name, fromlist=[''])
    klass = getattr(module, klass_name)

    return klass

