# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Bliss main package

.. autosummary::
    :toctree:

    comm
    common
    config
    controllers
    data
    physics
    scanning
    shell
    tango
"""
from . import release

__version__ = release.version
__author__ = release.author
__license__ = release.license
version_info = release.version_info

from gevent import monkey as _monkey

_monkey.patch_all(thread=False)

from redis import selector as _selector

_selector._DEFAULT_SELECTOR = _selector.SelectSelector

from bliss.common.proxy import Proxy as _Proxy


def get_current_session():
    from bliss.common import session

    return session.get_current_session()


current_session = _Proxy(get_current_session)

from bliss.common.alias import MapWithAliases as _MapWithAliases

global_map = _MapWithAliases(current_session)

from bliss.common.logtools import Log as _Log

global_log = _Log(map=global_map)


def logging_startup(
    log_level="WARNING", fmt="%(levelname)s %(asctime)-15s %(name)s: %(message)s"
):
    """
    Provides basicConfig functionality to bliss activating at proper level the root loggers
    """
    import logging  # this is not to pollute the global namespace

    # save log messages format
    global_log.set_log_format(fmt)
    global_log._LOG_DEFAULT_LEVEL = log_level  # to restore level of non-BlissLoggers

    # setting startup level for session and bliss logger
    logging.getLogger("session").setLevel(log_level)
    logging.getLogger("bliss").setLevel(log_level)

    # install an additional handler, only for debug messages
    # (debugon / debugoff)
    global_log.set_debug_handler(logging.StreamHandler())
