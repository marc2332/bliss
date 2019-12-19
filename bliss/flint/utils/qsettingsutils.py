# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Helper relative to QSettings"""

import logging
from silx.gui import qt

_logger = logging.getLogger(__name__)


def setNamedTuple(settings: qt.QSettings, data):
    """Write a named tuple into this settings"""
    for key, value in data._asdict().items():
        settings.setValue(key, value)


def namedTuple(settings: qt.QSettings, datatype, defaultData=None):
    """Read a named tuple from the requested type using this settings"""
    content = {}
    for key in datatype._fields:
        if not settings.contains(key):
            continue
        try:
            value = settings.value(key)
            content[key] = value
        except Exception:
            _logger.debug(
                "Error while reading key [%s] %s from settings",
                settings.group(),
                key,
                exc_info=True,
            )

    if len(content) == 0:
        return defaultData

    try:
        return datatype(**content)
    except Exception:
        _logger.debug(
            "Error while reading key [%s] %s from settings",
            settings.group(),
            key,
            exc_info=True,
        )
        return defaultData
