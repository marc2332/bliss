# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from functools import partial
from bliss.common.utils import autocomplete_property


class NamespaceWrapper(object):
    """Namespace which delegates attribute getting and setting to a getter and setter method.
    """

    def __new__(cls, key_list, getter, setter, autocomplete=False):
        cls = type(cls.__name__, (cls,), {})
        for key in key_list:
            if autocomplete:
                setattr(
                    cls,
                    key,
                    autocomplete_property(
                        fget=partial(getter, key=key), fset=partial(setter, key=key)
                    ),
                )
            else:
                # to avoid autocompletion
                setattr(
                    cls,
                    key,
                    property(
                        fget=partial(NamespaceWrapper._getter, key=key),
                        fset=partial(NamespaceWrapper._setter, key=key),
                    ),
                )
        return object.__new__(cls)

    def __init__(self, key_list, getter, setter, autocomplete=False):
        """
        key_list: list of attributes of the Namespace
        getter: function that takes key as arg
        setter: function that takes key, value as args
        """

        self.__key_list = key_list  # .copy()
        self.__getter = getter
        self.__setter = setter

    def _getter(self, key):
        return self.__getter(key)

    def _setter(self, value, key):
        return self.__setter(key, value)

    def __info__(self):
        """Namespace content as a string
        """
        res = ""
        for key in self.__key_list:
            val = self._getter(key)
            if val:
                res += "." + key + "     ('" + val + "')" + "\n"
            else:
                res += "." + key + "\n"
        return "Namespace containing:\n" + res
