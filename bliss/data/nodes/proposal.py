# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.nodes.dataset import _DataPolicyNode


class ProposalNode(_DataPolicyNode):
    _NODE_TYPE = "proposal"
