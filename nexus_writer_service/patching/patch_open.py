# -*- coding: utf-8 -*-
#
# This f is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import io
import builtins
import traceback
from functools import wraps
from . import monkey
from ..utils.logging_utils import print_err


OPEN_FILES = {}


def _patch_close(f):
    old_close = f.close

    @wraps(old_close)
    def close():
        name = f.name
        old_close()
        OPEN_FILES.pop(f)
        print_open_files(" AFTER CLOSING " + repr(name))

    f.close = close


def _tracking_open(old_open):
    @wraps(old_open)
    def tracking_open(*args, **kwargs):
        stack = traceback.extract_stack()
        stack.pop()
        f = old_open(*args, **kwargs)
        _patch_close(f)
        OPEN_FILES[f] = stack
        print_open_files(" AFTER OPENING " + repr(f.name))
        return f

    return tracking_open


def print_open_files(msg="", **kwargs):
    print_err("\n### {} OPEN FILES{}".format(len(OPEN_FILES), msg), **kwargs)
    sep = ""
    for f, stack in OPEN_FILES.items():
        stack = sep.join(traceback.format_list(stack))
        print_err("\n Open file {}:\n{}{}".format(repr(f.name), sep, stack), **kwargs)
    print_err("\n### END OPEN FILES\n", **kwargs)


def patch():
    newitem = _tracking_open(monkey.original(builtins, "open"))
    monkey.patch_item(builtins, "open", newitem)
    newitem = _tracking_open(monkey.original(io, "open"))
    monkey.patch_item(io, "open", newitem)
    # Cannot patch these:
    # monkey.patch_item(h5py.h5f, "open")
    # monkey.patch_item(h5py.h5f, "create")


def unpatch():
    monkey.unpatch_item(builtins, "open")
    monkey.unpatch_item(io, "open")
    # monkey.unpatch_item(h5py.h5f, "open")
    # monkey.unpatch_item(h5py.h5f, "create")
