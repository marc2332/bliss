# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2018 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import weakref

__all__ = ['default_chain_add_preset', 'default_set_preset_in_chain']

#Globals
DEFAULT_PRESET = weakref.WeakValueDictionary()


def default_chain_add_preset(preset):
    """
    Add some preset on the default chain.
    """
    global DEFAULT_PRESET
    DEFAULT_PRESET[id(preset)] = preset

def default_set_preset_in_chain(chain):
    """
    Use by the default_chain function in bliss.common.scans
    to add presets for standard scans (ascan,dscan...)
    """
    for preset in DEFAULT_PRESET.values():
        chain.add_preset(preset)
