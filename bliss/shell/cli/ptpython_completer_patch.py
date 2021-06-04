# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Patch to modify the behavior of the ptpython PythonCompleter
The code for def signature_toolbar corresponds to ptpython version 2.0.4
"""
from jedi.inference.compiled.access import (
    DirectObjectAccess,
    getattr_static,
    ALLOWED_DESCRIPTOR_ACCESS,
)
import ptpython.completer
import jedi

from bliss.common.utils import autocomplete_property

old_get_completions = ptpython.completer.PythonCompleter.get_completions


def NEWget_completions(self, document, complete_event):
    """
    Get Python completions. Hide those starting with "_" (unless user first types the underscore).
    """
    allow_underscore = document.text.endswith("_") or document.text.rpartition(".")[
        -1
    ].startswith("_")
    if allow_underscore:
        yield from old_get_completions(self, document, complete_event)
    else:
        yield from (
            c
            for c in old_get_completions(self, document, complete_event)
            if not c.text.startswith("_")
        )


ptpython.completer.PythonCompleter.get_completions = NEWget_completions

old_is_allowed_getattr = DirectObjectAccess.is_allowed_getattr


def NEWis_allowed_getattr(self, name, unsafe=False):
    is_get_descriptor, not_allowed = old_is_allowed_getattr(self, name, unsafe)
    if is_get_descriptor and not_allowed:
        attr, _ = getattr_static(self._obj, name)
        if autocomplete_property in type(attr).__bases__:
            not_allowed = False
    return is_get_descriptor, not_allowed


DirectObjectAccess.is_allowed_getattr = NEWis_allowed_getattr
jedi.Interpreter._allow_descriptor_getattr_default = False
jedi.inference.compiled.access.ALLOWED_DESCRIPTOR_ACCESS += (autocomplete_property,)
