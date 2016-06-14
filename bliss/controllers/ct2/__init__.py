# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""ct2 (P201/C208) ESRF PCI counter card
"""

from .ct2 import *
from .device import *

from . import release
__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
__doc__ = release.description
__copyright__ = release.copyright
del release
