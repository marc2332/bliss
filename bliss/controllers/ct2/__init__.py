# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright (c) : 2015
# Beamline Control Unit, European Synchrotron Radiation Facility
# BP 220, Grenoble 38043
# FRANCE
#
# Distributed under the terms of the GNU Lesser General Public License,
# either version 3 of the License, or (at your option) any later version.
# See LICENSE.txt for more info.

"""
The python module for the ct2 (P201/C208) ESRF PCI counter card
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
