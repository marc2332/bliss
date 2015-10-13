# -*- coding: utf-8 -*-
#
# This file is part of the CT2 project
#
# Copyright 2015 European Synchrotron Radiation Facility, Grenoble, France
#
# Distributed under the terms of the LGPL license.
# See LICENSE.txt for more info.

"""CT2 (P201/C208) ESRF counter card

CT2 (P201/C208) ESRF counter card TANGO device
"""

from . import release
from .CT2 import CT2, main

__version__ = release.version
__version_info__ = release.version_info
__author__ = release.author
