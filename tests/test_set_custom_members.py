# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.utils import set_custom_members, with_custom_members
from bliss.common.utils import object_attribute_get, object_attribute_set, object_method
import pytest


def test_set_custom_members():
    @with_custom_members
    class A:
        def __init__(self):
            self.been_called = False

        @property
        def a(self):
            self.been_called = True

        @object_attribute_set()
        def b(self):
            pass

        @object_attribute_get()
        def c(self):
            pass

        @staticmethod
        def d(self):
            pass

        @object_method
        def e(self):
            pass

        def f(self):
            pass

    @with_custom_members
    class B:
        pass

    aobj = A()
    bobj = B()

    set_custom_members(aobj, bobj)

    assert not aobj.been_called
    assert hasattr(bobj.e, "_object_method_")
    assert hasattr(bobj.c, "_object_attribute_")
    assert hasattr(bobj.b, "_object_attribute_")
    assert not hasattr(bobj, "f")
