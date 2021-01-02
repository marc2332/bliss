# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Base hook system. Check the doc to find
how to use motion hooks in your system"""

import sys
import weakref
import functools
import itertools
import collections
import contextlib
from bliss.common.logtools import *
from bliss import global_map

__all__ = ["MotionHook"]


def group_hooks(axes):
    hooks = collections.defaultdict(list)
    for axis in axes:
        for hook in axis.motion_hooks:
            hooks[hook].append(axis)
    return hooks


@contextlib.contextmanager
def execute_pre_hooks(hooks_dict, pre_method_name, post_method_name):
    # hooks_dict is { hook: [item, ...] }
    # each hook is executed by calling its "pre" method, with item list as argument ;
    # in case of error "post" methods are executed with same arguments
    executed_hooks = {}
    try:
        for hook, arg in hooks_dict.items():
            try:
                hook._init()
                getattr(hook, pre_method_name)(arg)
            except BaseException:
                raise
            finally:
                executed_hooks[hook] = arg

        yield
    except BaseException:
        if post_method_name:
            # let's call post_move for all executed hooks so far
            # (including this one), in reversed order
            for hook, arg in reversed(list(executed_hooks.items())):
                try:
                    getattr(hook, post_method_name)(arg)
                except BaseException:
                    sys.excepthook(*sys.exc_info())
        raise


@contextlib.contextmanager
def execute_pre_move_hooks(motions):
    hooks = {
        hook: [m for m in motions if m.axis in hook_axes]
        for hook, hook_axes in group_hooks(m.axis for m in motions).items()
    }
    with execute_pre_hooks(hooks, "pre_move", "post_move"):
        yield

class MotionHook:
    """
    Base motion hook. Executed before a motion starts and after motion ends.
    """

    def __init__(self):
        self.__axes = weakref.WeakValueDictionary()
        global_map.register(self, parents_list=["motion_hooks"])

    def _add_axis(self, axis):
        """Internal method to add a new axis to the hook. 
        Called by bliss when an axis is created, which is linked to this hook

        Args:
            axis (Axis): new axis to be added to the hook
        """
        self.__axes[axis.name] = axis
        global_map.register(self, children_list=list(self.axes.values()))

    @property
    def axes(self):
        """A dict<name, axis> with all axes that are controlled by this hook"""
        return self.__axes

    @functools.lru_cache(maxsize=1)
    def _init(self):
        return self.init()

    def init(self):
        """
        Called the first time the motion hook is activated. Overwrite in your
        sub-class.
        Default implementation does nothing.
        """

    def pre_move(self, motion_list):
        """
        Called during prepare_move procedure. Overwrite in your sub-class.
        Default implementation does nothing.
        """

    def post_move(self, motion_list):
        """
        Called after motion ends. Overwrite in your sub-class.
        Default implementation does nothing.
        """
