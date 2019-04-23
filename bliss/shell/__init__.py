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


from bliss import release
from bliss.config import static
from bliss.common.session import DefaultSession
from bliss.config.conductor.client import get_default_connection
from bliss.shell.bliss_banners import print_rainbow_banner


_log = logging.getLogger("bliss.shell")


def initialize(session_name=None):
    # Initialize user namespace with bliss.common.standard
    from bliss.common import standard

    user_ns = {name: getattr(standard, name) for name in standard.__all__}

    # Add config to the user namespace
    config = static.get_config()
    user_ns["config"] = config
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
        session = config.get(session_name)
        print("%s: Executing setup..." % session.name)

    try:
        session.setup(env_dict=user_ns, verbose=True)
    except Exception:
        error_flag = True
        sys.excepthook(*sys.exc_info())

    if error_flag:
        print("Warning: error(s) happened during setup, setup may not be complete.")
    else:
        print("Done.")
        print("")

    return user_ns, session
