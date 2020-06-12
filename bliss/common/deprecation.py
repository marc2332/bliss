# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Module to provide deprecation warning helper for the bliss project.
"""

import logging
import traceback

depreclog = logging.getLogger("bliss.deprecation")

deprecache = set([])

FORCE = False
"""If true, deprecation using only_once are also generated.
It is needed for reproducible tests.
"""


def deprecated_warning(
    kind: str,
    name: str,
    reason: str = None,
    replacement: str = None,
    since_version: str = None,
    only_once: bool = True,
    display_caller: bool = True,
    skip_backtrace_count: int = 0,
):
    """
    Function to log a deprecation warning

    Arguments:
        kind: Nature of the object to be deprecated:
            "Module", "Function", "Class" ...
        name: Object name.
        reason: Reason for deprecating this function
            (e.g. "feature no longer provided",
        replacement: Name of replacement function (if the reason for
            deprecating was to rename the function)
        since_version: First *bliss* version for which the function was
            deprecated (e.g. "0.5.0").
        only_once: If true, the deprecation warning will only be
            generated one time for each different call locations.
            Default is true.
        display_caller: If true display the line calling the deprecated
            object
        skip_backtrace_count: Amount of last backtrace to ignore when
            logging the backtrace
    """
    if not depreclog.isEnabledFor(logging.WARNING):
        # Avoid computation when it is not logged
        return

    kind = kind.capitalize()
    msg = f"{kind} {name} is deprecated"
    if since_version is not None:
        msg += f" since BLISS version {since_version}"
    msg += "."
    if reason is not None:
        msg += f" Reason: {reason}."
    if replacement is not None:
        msg += f" Use '{replacement}' instead."

    if display_caller:
        limit = 2 + skip_backtrace_count
        stack = traceback.format_stack(limit=limit)
        if len(stack) >= 1:
            caller = stack[0]
            if "<stdin>" not in caller:
                # If it is not a command typed from the shell
                caller = caller.rstrip()
                msg += f"\n{caller}"

    if not FORCE and only_once:
        if msg in deprecache:
            return
        else:
            deprecache.add(msg)

    depreclog.warning(msg)
