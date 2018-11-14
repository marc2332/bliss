# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import sys

if os.name == "posix" and sys.version_info[0] < 3:
    from subprocess32 import *
else:
    from .subprocess import *
