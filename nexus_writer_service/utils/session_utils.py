# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Activate Bliss session utilities
"""

from functools import wraps
from bliss import current_session


def with_scan_saving(func):
    """Pass the current session's SCAN_SAVING instance as a named argument

    :param callable func:
    :returns callable:
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        scan_saving = kwargs.get("scan_saving")
        if scan_saving is None:
            if current_session:
                kwargs["scan_saving"] = current_session.scan_saving
            else:
                raise RuntimeError("No activate Bliss session")
        return func(*args, **kwargs)

    return wrapper


@with_scan_saving
def scan_saving_get(attr, default=None, scan_saving=None):
    """Get attribute from the session's scan saving object

    :param str attr:
    :param default:
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns str:
    """
    return getattr(scan_saving, attr, default)


@with_scan_saving
def dataset_get(attr, default=None, scan_saving=None):
    """Get attribute from the session's dataset object

    :param str attr:
    :param default:
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns str:
    """
    try:
        return scan_saving.dataset[attr]
    except (AttributeError, KeyError):
        return default
