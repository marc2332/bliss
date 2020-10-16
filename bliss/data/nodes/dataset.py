# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data.node import DataNodeContainer


class _DataPolicyNode(DataNodeContainer):
    _NODE_TYPE = NotImplemented

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)

    @property
    def metadata(self):
        return {k: v for k, v in self.info.items() if not k.startswith("__")}

    @property
    def metadata_fields(self):
        return {k for k in self.info.keys() if not k.startswith("__")}


class DatasetNode(_DataPolicyNode):
    _NODE_TYPE = "dataset"

    @property
    def is_closed(self):
        return self.info.get("__closed__", False)

    @property
    def techniques(self):
        return self.info.get("__techniques__", set())
