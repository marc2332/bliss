# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

'''Shell (:term:`CLI` and Web based)'''

import os
import yaml
import sys
import logging
import functools

from bliss import setup_globals

try:
    from bliss.config import static
except ImportError:
    sys.excepthook(*sys.exc_info())

try:
    from tabulate import tabulate
except ImportError:
    pass

_log = logging.getLogger('bliss.shell')

def initialize(*session_names):
    config = static.get_config()
    user_ns = { "config": config }
    sessions = list()
    for sname in session_names:
        session = config.get(sname)
        session.setup(env_dict = user_ns,verbose = True)
        sessions.append(session)
    return user_ns,sessions
