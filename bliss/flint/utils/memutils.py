# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provides helper function to check the memory
"""


def patch_count_qobject_instance(base_class):
    """
    Patch a QObject class to count new created instances.

    Class attributes `SUM_INSTANCE`, `ALIVE_INSTANCE` is added to the class.
    """
    if hasattr(base_class, "ALIVE_INSTANCE"):
        return
    old_constructor = base_class.__init__
    base_class.ALIVE_INSTANCE = 0
    base_class.SUM_INSTANCE = 0

    def remove_ref():
        base_class.ALIVE_INSTANCE -= 1

    def new_constructor(self, *args, **kwargs):
        old_constructor(self, *args, **kwargs)
        base_class.SUM_INSTANCE += 1
        base_class.ALIVE_INSTANCE += 1
        self.destroyed.connect(remove_ref)

    base_class.__init__ = new_constructor


def count_qobject_instance(base_class):
    """
    Decorator to count instances from QObject class.

    A class attribute `NB_DATA` is added to the class.

    .. code-block:: python

        @count_qobject_instance
        class Foo(qt.QObject):
            pass
    """
    patch_count_qobject_instance(base_class)
    return base_class
