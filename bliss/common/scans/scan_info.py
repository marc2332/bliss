# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Contains helper to manage the `scan_info` metadata provided inside each scans.

Backward compatibility module created for BLISS 1.7. Can be removed in few
version.
"""

import typing
from bliss.scanning.scan_info import ScanInfo as _ScanInfo
from bliss.common import deprecation


class ScanInfoFactory(_ScanInfo):
    def __init__(self, scan_info: typing.Dict):
        super(ScanInfoFactory, self).__init__()
        self._set_scan_info(scan_info)

        deprecation.deprecated_warning(
            kind="Class",
            name="ScanInfoFactory",
            reason="scan_info dict can be replaced by bliss.scanning.scan_info.ScanInfo which provide ScanInfoFactory API",
            since_version="1.7",
            only_once=False,
            skip_backtrace_count=1,
        )
