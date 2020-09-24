# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.node import DataNodeContainer


class DatasetNode(DataNodeContainer):
    _NODE_TYPE = "dataset"

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)

    @property
    def metadata(self):
        return dict(
            filter(lambda elem: not elem[0].startswith("__"), self.info.items())
        )

    @property
    def is_closed(self):
        return self.info.get("__closed__", False)

    @property
    def techniques(self):
        return self.info.get("__techniques__", set())
