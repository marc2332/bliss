# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import re
from bliss.data.node import DataNodeContainer


class _DataPolicyNode(DataNodeContainer):
    _NODE_TYPE = NotImplemented

    def __init__(self, name, **kwargs):
        super().__init__(self._NODE_TYPE, name, **kwargs)

    @property
    def metadata(self):
        return self.get_metadata()

    @property
    def metadata_fields(self):
        return self.get_metadata_fields()

    def get_metadata(self, pattern=None):
        """
        :param str pattern: regex pattern for field name
        :returns dict:
        """
        is_valid = self._field_name_filter(pattern=pattern)
        return {k: v for k, v in self.info.items() if is_valid(k)}

    def get_metadata_fields(self, pattern=None):
        """
        :param str pattern: regex pattern for field name
        :returns set:
        """
        is_valid = self._field_name_filter(pattern=pattern)
        return {k for k in self.info.keys() if is_valid(k)}

    def _field_name_filter(self, pattern=None):
        """
        :param str pattern: regex pattern for field name
        :returns callable:
        """
        if pattern:
            pattern_obj = re.compile(pattern)
            return lambda name: not name.startswith("__") and pattern_obj.match(name)
        else:
            return lambda name: not name.startswith("__")


class DatasetNode(_DataPolicyNode):
    _NODE_TYPE = "dataset"

    @property
    def is_closed(self):
        return self.info.get("__closed__", False)

    @property
    def techniques(self):
        return self.info.get("__techniques__", set())

    @techniques.setter
    def techniques(self, names: set):
        self.info["__techniques__"] = names

    def add_technique(self, name):
        self.techniques |= {name}
