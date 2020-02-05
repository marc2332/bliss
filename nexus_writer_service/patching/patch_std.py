# -*- coding: utf-8 -*-
#
# This f is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import sys
import builtins
import logging
from functools import wraps
from . import monkey
from ..utils import logging_utils


def _print_out(old_print, logger=None):
    if logger is None:
        stream = logging_utils.out_stream
    else:
        stream = logging_utils.textstream_wrapper(logger, logging.INFO)

    @wraps(old_print)
    def print_out(*args, file=None, **kwargs):
        if file is None:
            file = stream
        return old_print(*args, file=file, **kwargs)

    return print_out


def patch_stdout(logger=None):
    monkey.patch_item(sys, "stdout", logging_utils.out_stream)


def patch_stderr(logger=None):
    monkey.patch_item(sys, "stderr", logging_utils.err_stream)


def patch_print():
    newitem = _print_out(monkey.original(builtins, "print"))
    monkey.patch_item(builtins, "print", newitem)


def patch(logger=None, stdout=True, stderr=True):
    if stdout:
        patch_stdout()
        # When patching stdout there is no need to patch print
        # patch_print(logger=logger)
    if stderr:
        patch_stderr()


def unpatch():
    monkey.unpatch_item(sys, "stdout")
    monkey.unpatch_item(sys, "stderr")
