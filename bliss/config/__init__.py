# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Heart of the bliss configuration (both :mod:`~bliss.config.static` and \
:mod:`~bliss.config.settings`)

.. autosummary::
    :toctree:

    beacon_object
    channels
    conductor
    plugins
    settings
    static
"""


def get_sessions_list():
    """Return a list of available sessions found in config"""
    all_sessions = list()
    from bliss.config import static

    config = static.get_config()
    for name in config.names_list:
        c = config.get_config(name)
        if c.get("class") != "Session":
            continue
        if c.get_inherited("plugin") != "session":
            continue
        all_sessions.append(name)

    return all_sessions
