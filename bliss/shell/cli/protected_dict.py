# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import functools

"""
The aim is to implement a dict where some keys are protected from simple
overwriting.
"""


class ProtectedDictType(type):
    class DictProxyClass(object):
        def __init__(self, wrapped, protected_keys):
            """
                wrapped: dict
                protected_keys: set of protected keys
            """
            self._wrapped = wrapped
            self._protected_keys = (
                set(protected_keys)
                .union(preprotected_keys())
                .intersection(self._wrapped.keys())
            )

        def proxy(self, attr, *args):
            return getattr(self._wrapped, attr)(*args)

        def proxy_property(self, attr):
            return getattr(self._wrapped, attr)

        def setitem(self, key, value):
            if key not in self._protected_keys:
                self._wrapped[key] = value
            else:
                raise RuntimeError(f"{key} is protected and can not be modified!")

    def repartial(func, parameter):
        @functools.wraps(func)
        def wrapped(self, *args, **kw):
            return func(self, parameter, *args, **kw)

        return wrapped

    def __new__(cls, name, bases, attrs):
        return super(ProtectedDictType, cls).__new__(
            cls, name, (ProtectedDictType.DictProxyClass,) + bases, attrs
        )

    def __init__(cls, name, bases, attrs):
        setattr(cls, "__setitem__", cls.setitem)
        untouched = (
            "__new__",
            "__init__",
            "__class__",
            "__setitem__",
            "__setattr__",
            "__getattribute__",
        )
        for attributeName in dir(dict()):
            if (
                callable(getattr(dict(), attributeName))
                and attributeName not in untouched
            ):
                setattr(
                    cls,
                    attributeName,
                    ProtectedDictType.repartial(cls.proxy, attributeName),
                )
            elif attributeName not in untouched:
                setattr(
                    cls,
                    attributeName,
                    property(
                        ProtectedDictType.repartial(cls.proxy_property, attributeName)
                    ),
                )


class ProtectedDict(dict, metaclass=ProtectedDictType):
    def use_as_wrapped(self, wrapped):
        """swapp the wrapped dict"""
        self._wrapped = wrapped

    def protect_many(self, keys):
        """add a key to the inventory of protected keys"""
        new_keys = set(keys).intersection(self._wrapped.keys())
        self._protected_keys.update(new_keys)

    def protect(self, key):
        """add a key to the inventory of protected keys"""
        assert isinstance(key, str)
        assert key in self._wrapped.keys()
        self._protected_keys.add(key)

    def unprotect(self, key):
        """remove a key from the inventory of protected keys"""
        assert key in self._protected_keys
        self._protected_keys.remove(key)

    def is_protected(self, key):
        return key in self._protected_keys

    @property
    def wrapped_dict(self):
        return self._wrapped


#### helper/placeholder to protect keys just after setup

_BLISS_SHELL_FUTUR_PROTECTED_ENV_DICT_KEYS = set()


def protect_after_setup(keys):
    global _BLISS_SHELL_FUTUR_PROTECTED_ENV_DICT_KEYS
    if isinstance(keys, str):
        _BLISS_SHELL_FUTUR_PROTECTED_ENV_DICT_KEYS.add(keys)
    else:
        _BLISS_SHELL_FUTUR_PROTECTED_ENV_DICT_KEYS.update(keys)


def preprotected_keys():
    return _BLISS_SHELL_FUTUR_PROTECTED_ENV_DICT_KEYS
