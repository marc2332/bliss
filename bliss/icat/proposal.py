# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.icat.policy import DataPolicyObject


class Proposal(DataPolicyObject):

    NODE_TYPE = "proposal"

    @property
    def sample_nodes(self):
        yield from self._node.children()

    @property
    def has_samples(self):
        try:
            next(self.sample_nodes)
        except StopIteration:
            return False
        else:
            return True
