# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.logtools import log_debug, log_warning
from bliss.common.utils import autocomplete_property
from bliss.common.namespace_wrapper import NamespaceWrapper


class DataPolicyObject:
    """A data policy object with a Redis representation that
    allows for storing ICAT metadata fields
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

    def __setitem__(self, key, value):
        """Set metadata field in Redis"""
        self.write_metadata_field(key, value)

    def __getitem__(self, key):
        """Get metadata field from Redis"""
        return self._node.info[key]

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

    def _log_warning(self, msg):
        log_warning(self, f"{self._NODE_TYPE}({self}): {msg}")

    def get_current_icat_metadata(self):
        """Get all metadata key-value pairs from Redis
        """
        return self._node.metadata

    def write_metadata_field(self, key, value):
        """Store metadata key-value pair in Redis
        """
        if value is None:
            if key in self._node.info:
                self._node.info.pop(key)
            return

        assert self.validate_fieldname(
            key
        ), f"{repr(key)} is not an accepted key for ICAT"
        assert isinstance(
            value, str
        ), f"{repr(value)} is not an accepted value for ICAT (only strings are allowed)"
        self._node.info[key] = value

    def validate_fieldname(self, fieldname):
        return False

    @property
    def expected_fields(self):
        """all required metadata fields"""
        return set()

    @autocomplete_property
    def expected(self):
        """namespace to read/write expected metadata fields"""
        return NamespaceWrapper(
            self.expected_fields, self._node.info.get, self.write_metadata_field
        )

    @property
    def existing_fields(self):
        """all existing metadata fields"""
        return set(self._node.metadata.keys())

    @autocomplete_property
    def existing(self):
        """namespace to read/write existing metadata fields"""
        return NamespaceWrapper(
            self._node.metadata.keys(), self._node.info.get, self.write_metadata_field
        )

    @property
    def missing_fields(self):
        """returns a list of required metadata fields that are not yet filled"""
        return self.expected_fields.difference(self.existing_fields)

    @autocomplete_property
    def missing(self):
        """namespace to read/write mising metadata fields"""
        return NamespaceWrapper(
            self.missing_fields, self._node.info.get, self.write_metadata_field
        )

    def check_metadata_consistency(self):
        """returns True when all required metadata fields are filled"""
        mtf = self.missing_fields
        if mtf:
            self._log_warning(
                f"The following metadata fields are expected by a given technique but not provided: {mtf}"
            )
        return not mtf
