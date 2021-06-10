# -*- coding: utf-8 -*-
#
# This f is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout De Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""After importing this module, `subprocess` will be the
original and Bliss will not patch it.
"""

import bliss  # unused but needed
import subprocess
from nexus_writer_service.patching.gevent import unpatch_module

unpatch_module(subprocess, "subprocess")
