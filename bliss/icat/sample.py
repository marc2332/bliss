# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.icat.policy import DataPolicyObject
from bliss.icat.proposal import Proposal


class Sample(DataPolicyObject):

    _NODE_TYPE = "sample"

    @property
    def proposal(self):
        return Proposal(self._node.parent)

    @property
    def dataset_nodes(self):
        yield from self._node.children()

    @property
    def has_datasets(self):
        try:
            next(self.dataset_nodes)
        except StopIteration:
            return False
        else:
            return True
