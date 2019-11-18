# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.nodes.scan import Scan
from bliss.data.node import DataNodeContainer


class GroupScan(Scan):
    _NODE_TYPE = "scan_group"
