# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Modules containing constants used in the project.

It is only using  basic python types, to avoid dependencies.
"""

DEFAULT_SESSION_NAME = "__DEFAULT__"
"""Name of the default session used by BLISS (which typing `bliss` without
arguments)

This was chosen to not collide a name scientists could use in beamlines.

This name is not part of the sessions listed by `get_sessions_list`, as it is
not a session from the config.
"""
