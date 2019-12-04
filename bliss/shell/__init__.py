# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""Shell (:term:`CLI` and Web based)"""

import os
import sys
import logging
import platform


if sys.platform not in ["win32", "cygwin"]:
    from blessings import Terminal
else:

    class Terminal:
        def __getattr__(self, prop):
            if prop.startswith("__"):
                raise AttributeError(prop)
            return ""


from gevent import socket
import functools
from bliss import release, current_session
from bliss.config import static
from bliss.common import session
from bliss.common.session import DefaultSession
from bliss.config.conductor.client import get_default_connection
from bliss.shell.bliss_banners import print_rainbow_banner
import __main__

_log = logging.getLogger("bliss.shell")


session.set_current_session = functools.partial(
    session.set_current_session, force=False
)


def initialize(session_name=None):
    # Add config to the user namespace
    config = static.get_config()
    error_flag = False

    """ BLISS CLI welcome messages """

    t = Terminal()

    # Version
    _version = "version %s" % release.short_version

    # Hostname
    _hostname = platform.node()

    # Beacon host/port
    try:
        _host = get_default_connection()._host
        _port = str(get_default_connection()._port)
    except:
        _host = "UNKNOWN"
        _port = "UNKNOWN"

    # Conda environment
    try:
        _conda_env = (
            "(in {t.blue}%s{t.normal} Conda environment)".format(t=t)
            % os.environ["CONDA_DEFAULT_ENV"]
        )
    except KeyError:
        _conda_env = ""

    print_rainbow_banner()
    print("")
    print(
        "Welcome to BLISS %s running on {t.blue}%s{t.normal} %s".format(t=t)
        % (_version, _hostname, _conda_env)
    )
    print("Copyright (c) 2015-2019 Beamline Control Unit, ESRF")
    print("-")
    print(
        "Connected to Beacon server on {t.blue}%s{t.normal} (port %s)".format(t=t)
        % (_host, _port)
    )

    """ Setup(s) """
    if session_name is None:
        session = DefaultSession()
    else:
        # we will lock the session name
        # this will prevent to start serveral bliss shell
        # with the same session name
        # lock will only be released at the end of process
        default_cnx = get_default_connection()
        try:
            default_cnx.lock(session_name, timeout=1.)
        except RuntimeError:
            try:
                lock_dict = default_cnx.who_locked(session_name)
            except RuntimeError:  # Beacon is to old to answer
                raise RuntimeError(f"{session_name} is already started")
            else:
                raise RuntimeError(
                    f"{session_name} is already running on %s"
                    % lock_dict.get(session_name)
                )
        # set the client name to somethings useful
        try:
            default_cnx.set_client_name(
                f"host:{socket.gethostname()},pid:{os.getpid()} cmd: **bliss -s {session_name}**"
            )
        except RuntimeError:  # Beacon is too old
            pass
        session = config.get(session_name)
        print("%s: Executing setup..." % session.name)

    env_dict = __main__.__dict__

    exec("from bliss.shell.standard import *", env_dict)
    from bliss.scanning.scan import ScanDisplay

    env_dict["SCAN_DISPLAY"] = ScanDisplay(session.name)

    env_dict["history"] = lambda: print("Please press F3-key to view history!")

    try:
        session.setup(env_dict, verbose=True)
    except Exception:
        error_flag = True
        sys.excepthook(*sys.exc_info())

    if error_flag:
        print("Warning: error(s) happened during setup, setup may not be complete.")
    else:
        print("Done.")
        print("")

    env_dict["SCANS"] = current_session.scans

    return session.env_dict, session
