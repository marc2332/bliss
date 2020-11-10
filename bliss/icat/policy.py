# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.common.logtools import log_debug, log_warning
from bliss.common.utils import autocomplete_property
from bliss.common.namespace_wrapper import NamespaceWrapper
from bliss.icat.definitions import Definitions


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
        self.definitions = Definitions()
        self._expected_field = set()

    def __str__(self):
        return self.name

    def __setitem__(self, key, value):
        """Set metadata field in Redis"""
        self.write_metadata_field(key, value)

    def __getitem__(self, key):
        """Get metadata field from Redis"""
        return self.read_metadata_field(key)

    def __contains__(self, key):
        """Check metadata field in Redis"""
        return self.has_metadata_field(key)

    @property
    def name(self):
        return self._node.info["__name__"]

    @property
    def path(self):
        return self._node.info["__path__"]

    @property
    def node(self):
        return self._node

    @property
    def is_frozen(self):
        """Forzen means it does take metadata fields from its parent
        """
        return self._node.info.get("__frozen__")

    def _log_debug(self, msg):
        log_debug(self, f"{self._NODE_TYPE}({self}): {msg}")

    def _log_warning(self, msg):
        log_warning(self, f"{self._NODE_TYPE}({self}): {msg}")

    @property
    def parent(self):
        return None

    def get_current_icat_metadata(self, pattern=None):
        """Get all metadata key-value pairs from Redis (self and parents)
        """
        if not self.is_frozen and self.parent:
            metadata = self.parent.get_current_icat_metadata(pattern=pattern)
            metadata.update(self._node.get_metadata(pattern=pattern))
        else:
            metadata = self._node.get_metadata(pattern=pattern)
        return metadata

    def get_current_icat_metadata_fields(self, pattern=None):
        """Get all metadata field names from Redis (self and parents).
        """
        metadata_fields = self._node.get_metadata_fields(pattern=pattern)
        if not self.is_frozen and self.parent:
            metadata_fields |= self.parent.get_current_icat_metadata_fields(
                pattern=pattern
            )
        return metadata_fields

    def freeze_inherited_icat_metadata(self):
        """After this, changes in the parent metadata no longer affect
        the current metadata.
        """
        if self.is_frozen or not self.parent:
            return
        self_fields = self._node.get_metadata_fields()
        parent_fields = self.parent.get_current_icat_metadata_fields()
        for key in parent_fields - self_fields:
            value = self.parent.read_metadata_field(key)
            self.write_metadata_field(key, value)
        self._node.info["__frozen__"] = True

    def unfreeze_inherited_icat_metadata(self):
        """After this, the parent metadata affect the current metadata.
        """
        self._node.info["__frozen__"] = False

    def has_metadata_field(self, key):
        """Check metadata field exists in Redis (self and parents).
        """
        return key in self.get_current_icat_metadata_fields()

    def read_metadata_field(self, key):
        """Get the value of one metadata field from Redis (self and parents).
        Raises `KeyError` when field is missing.
        """
        try:
            return self._node.info[key]
        except KeyError:
            if self.parent:
                return self.parent.read_metadata_field(key)
            else:
                raise

    def get_metadata_field(self, key, default=None):
        """Get the value of one metadata field from Redis (self and parents).
        Returns `default` when field is missing.
        """
        try:
            return self.read_metadata_field(key)
        except KeyError:
            return default

    def write_metadata_field(self, key, value):
        """Store metadata key-value pair in Redis. Does not affect the parent.
        Remove key when the value is `None`.
        Raises `KeyError` when the key is not valid.
        Raises `ValueError` when the value is not a string.
        """
        if value is None:
            self.remove_metadata_field(key)
            return
        if not isinstance(value, str):
            raise ValueError(
                f"{repr(value)} is not an accepted value for ICAT (only strings are allowed)"
            )
        if not self.validate_fieldname(key):
            raise KeyError(f"{repr(key)} is not an accepted key for ICAT")
        self._node.info[key] = value

    def remove_metadata_field(self, key):
        """Remove a metadata field from Redis if it exists.
        Does not affect the parents.
        """
        self._node.info.pop(key, None)

    def remove_all_metadata_fields(self):
        """Remove a metadata field from Redis if it exists.
        Does not affect the parents.
        """
        for key in self.get_current_icat_metadata_fields():
            self.remove_metadata_field(key)

    def validate_fieldname(self, fieldname):
        return fieldname in self.definitions.all

    @autocomplete_property
    def all(self):
        """namespace to access all possible keys"""
        return NamespaceWrapper(
            self.definitions.all, self.get_metadata_field, self.write_metadata_field
        )

    @property
    def expected_fields(self):
        """all required metadata fields"""
        if self.parent:
            return self._expected_field | self.parent.expected_fields
        else:
            return self._expected_field

    @autocomplete_property
    def expected(self):
        """namespace to read/write expected metadata fields"""
        return NamespaceWrapper(
            self.expected_fields, self.get_metadata_field, self.write_metadata_field
        )

    @property
    def existing_fields(self):
        """all existing metadata fields"""
        return self.get_current_icat_metadata_fields()

    @autocomplete_property
    def existing(self):
        """namespace to read/write existing metadata fields"""
        return NamespaceWrapper(
            self.existing_fields, self.get_metadata_field, self.write_metadata_field
        )

    @property
    def missing_fields(self):
        """returns a list of required metadata fields that are not yet filled"""
        return self.expected_fields.difference(self.existing_fields)

    @autocomplete_property
    def missing(self):
        """namespace to read/write mising metadata fields"""
        return NamespaceWrapper(
            self.missing_fields, self.get_metadata_field, self.write_metadata_field
        )

    def check_metadata_consistency(self):
        """returns True when all required metadata fields are filled"""
        mtf = self.missing_fields
        if mtf:
            self._log_warning(
                f"The following metadata fields are expected by a given technique but not provided: {mtf}"
            )
        return not mtf

    @property
    def metadata_is_complete(self):
        return not self.missing_fields
