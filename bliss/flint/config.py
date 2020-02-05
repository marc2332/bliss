# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Provide some configuration purpose for Flint.

This module must not have dependancy to Qt or OpenGL, or matplotlib cause it is
used by bliss.
"""

import os
import platform
from argparse import ArgumentParser
import bliss.release


def configure_parser_arguments(parser: ArgumentParser):
    version = "flint - bliss %s" % (bliss.release.short_version)
    parser.add_argument("-V", "--version", action="version", version=version)
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Set logging system in debug mode",
    )
    parser.add_argument(
        "--enable-opengl",
        "--gl",
        dest="opengl",
        action="store_true",
        default=False,
        help="Enable OpenGL rendering. It provides a faster rendering for plots "
        "but could have issue with remote desktop (default: matplotlib is used)",
    )
    parser.add_argument(
        "--enable-simulator",
        dest="simulator",
        action="store_true",
        default=False,
        help="Enable scan simulation panel",
    )
    parser.add_argument(
        "--enable-gevent-poll",
        dest="gevent_poll",
        action="store_true",
        default=False,
        help="Enable system patching of the 'poll' function in order to create a cooperative event loop between Qt and gevent. "
        "It processes efficiently events from fast acquisition scans but could be unstable "
        "(experimental)",
    )
    parser.add_argument(
        "--matplotlib-dpi",
        type=int,
        dest="matplotlib_dpi",
        default=None,
        help="Set the DPI used for the matplotlib backend. "
        "This value will be stored in the user preferences (default: 100)",
    )
    parser.add_argument(
        "--clear-settings",
        action="store_true",
        dest="clear_settings",
        default=False,
        help="Start with cleared local user settings. ",
    )


def get_flint_key(pid=None) -> str:
    """Reach the key name storing the address of the RPC server
    providing access to the flint API.
    """
    hostname = platform.node()
    username = os.environ.get("USER")
    if pid is None:
        pid = os.getpid()
    return f"flint:{hostname}:{username}:{pid}"


def get_workspace_key(session_name: str) -> str:
    """Returns the base key prefix used to store workspace information in Redis
    """
    return f"flint.{session_name}.workspace"
