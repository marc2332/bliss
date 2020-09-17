# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout De Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from contextlib import contextmanager
import gevent.monkey


def unpatch_module(module, name):
    """Undo gevent monkey patching of this module

    :param module:
    :param str name: the name given by gevent to this module
    """
    original_module_items = gevent.monkey.saved.pop(name, None)
    if not original_module_items:
        return
    for attr, value in original_module_items.items():
        setattr(module, attr, value)


def repatch_module(module, name):
    """Redo gevent monkey patching of this module,
    whether it is already patched or not.

    :param module:
    :param str name: the name given by gevent to this module
    """
    unpatch_module(module, name)
    gevent.monkey._patch_module(name)


@contextmanager
def original_module(module, name):
    """Use the original module within this context

    :param module:
    :param str name: the name given by gevent to this module
    """
    unpatch_module(module, name)
    try:
        yield
    finally:
        repatch_module(module, name)
