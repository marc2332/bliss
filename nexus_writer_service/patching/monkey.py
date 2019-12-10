# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import importlib

_originals = {}


def patch_item(module, attr, newitem):
    try:
        olditem = getattr(module, attr)
    except KeyError:
        pass
    else:
        _originals.setdefault(module.__name__, {}).setdefault(attr, olditem)
    setattr(module, attr, newitem)


def unpatch_item(module, attr):
    try:
        olditem = _originals[module.__name__].get(attr)
    except KeyError:
        pass
    else:
        setattr(module, attr, olditem)


def original(module, attr):
    try:
        return _originals[module.__name__][attr]
    except KeyError:
        return getattr(module, attr)


def patched(module, attr):
    return getattr(module, attr) != original(module, attr)


def patch(name, **kwargs):
    module = importlib.import_module(__package__ + ".patch_" + name)
    module.patch(**kwargs)


def unpatch(name, **kwargs):
    module = importlib.import_module(__package__ + ".patch_" + name)
    module.unpatch(**kwargs)
