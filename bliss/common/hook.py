# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Base hook system"""

import weakref


__all__ = ['MotionHook']


class MotionHook(object):
    """
    Base motion hook. Executed before a motion starts and after motion ends.
    """
    def __init__(self):
        self.__axes = weakref.WeakValueDictionary()

    def add_axis(self, axis):
        """Add a new axis to the hook"""
        self.__axes[axis.name] = axis

    @property
    def axes(self):
        """A dict<name, axis> with all axes that are controlled by this hook"""
        return self.__axes

    def pre_move(self, *motion_list):
        """
        Called during prepare_move procedure. Overwrite in your sub-class.
        Default implementation does nothing.
        """

    def post_move(self, *motion_list):
        """
        Called after motion ends. Overwrite in your sub-class.
        Default implementation does nothing.
        """
