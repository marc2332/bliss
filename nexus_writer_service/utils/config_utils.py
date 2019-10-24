# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Bliss session configuration utilities
"""

from bliss.common.session import get_current_session
from bliss.config import static


def static_config():
    """
    Get static config

    :returns bliss.config.static.Config:
    """
    return static.get_config()


def static_config_root():
    """
    Get root node of session's static config

    :returns bliss.config.static.Node:
    """
    return static_config().root


def scan_saving():
    """
    Get session's SCAN_SAVING object

    :returns bliss.scanning.scan.ScanSaving:
    """
    return get_current_session().env_dict['SCAN_SAVING']


def scan_saving_get(attr, default=None):
    """
    Get attribute from the session's scan saving object

    :returns str:
    """
    return getattr(scan_saving(), attr, default)
