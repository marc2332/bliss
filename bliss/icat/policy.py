# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.logtools import log_debug
from bliss.common.utils import autocomplete_property


class DataPolicyObject:
    """A data policy object with a Redis representation
    """

    _REQUIRED_INFO = {"__name__", "__path__"}
    _NODE_TYPE = NotImplemented

    def __init__(self, node):
        """
        :param DataNodeContainer node:
        """
        self._node = node
        node_type = node.type
        if node_type != self._NODE_TYPE:
            raise RuntimeError(
                f"Node type must be '{self._NODE_TYPE}' instead of '{node_type}'"
            )
        existing = set(node.info.keys())
        undefined = self._REQUIRED_INFO - existing
        if undefined:
            raise RuntimeError(f"Missing node info: {undefined}")

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self._node.info.get("__name__")

    @property
    def path(self):
        return self._node.info.get("__path__")

    @autocomplete_property
    def node(self):
        return self._node

    def _log_debug(self, msg):
        log_debug(self, f"{self._NODE_TYPE}({self}): {msg}")
