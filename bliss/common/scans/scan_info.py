# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Contains helper to manage the `scan_info` metadata provided inside each scans.
"""

import typing
from bliss.scanning.scan_info import ScanInfo


class ScanInfoFactory(ScanInfo):
    def __init__(self, scan_info: typing.Dict):
        super(ScanInfoFactory, self).__init__()
        self._set_scan_info(scan_info)
