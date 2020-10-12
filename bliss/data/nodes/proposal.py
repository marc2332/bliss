# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.node import DataNodeContainer


class ProposalNode(DataNodeContainer):
    _NODE_TYPE = "proposal"

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)
