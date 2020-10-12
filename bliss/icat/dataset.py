# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import datetime
from bliss import current_session
from bliss.common.logtools import log_warning
from bliss.icat import FieldGroup
from bliss.icat.definitions import Definitions
from bliss.common.utils import autocomplete_property
from types import SimpleNamespace
from bliss.icat.policy import DataPolicyObject
from bliss.icat.sample import Sample


class CustomSetterNamespace(SimpleNamespace):
    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if (
            not (key.startswith("__") or key.startswith("_CustomSetterNamespace__"))
            and self.__init_done
        ):
            if key in self.__key_list:
                self.__setter(key, value)
            else:
                raise AttributeError(f"AttributeError: no attribute '{key}'")

    def __getattribute__(self, key):
        if (
            key.startswith("__")
            or key.startswith("_CustomSetterNamespace__")
            or not self.__init_done
        ):
            return super().__getattribute__(key)
        else:
            return self.__getter(key)

    def __init__(self, key_list, getter, setter, init_value_dict=None):
        """
            key_list: list of attributes of the Namespace
            getter: function that takes key as arg
            setter: function that takes key, value as arg
            init_value_dict: values that are taken during init (if provided)
        """
        self.__key_list = key_list
        self.__getter = getter
        self.__setter = setter
        if init_value_dict:
            init_values = init_value_dict.copy()
            for key in key_list:
                if key not in init_values:
                    init_values[key] = None
        else:
            init_values = dict()
            for key in key_list:
                init_values[key] = getter(key)

        self.__init_done = False
        super().__init__(**init_values)
        self.__init_done = True

    @property
    def __dict__(self):
        return dict(
            filter(
                lambda elem: not elem[0].startswith("_CustomSetterNamespace__"),
                super().__dict__.items(),
            )
        )

    def __info__(self):
        res = ""
        for key in self.__dict__.keys():
            val = self.__getter(key)
            if val:
                res += "." + key + "     ('" + val + "')" + "\n"
            else:
                res += "." + key + "\n"
        return "Namespace containing:\n" + res


class Dataset(DataPolicyObject):

    REQUIRED_INFO = DataPolicyObject.REQUIRED_INFO | {"__closed__"}
    NODE_TYPE = "dataset"

    def __init__(self, node):
        super().__init__(node)
        self.definitions = Definitions()

    def gather_metadata(self):
        """Initialize the dataset node info"""

        if self.is_closed:
            raise RuntimeError("The dataset is already closed")

        if self._node.info.get("__metadata_gathered__"):
            raise RuntimeError("metadata for this dataset has already been collected!")

        if current_session.icat_mapping:
            metadata = current_session.icat_mapping.get_metadata()
        else:
            metadata = dict()

        metadata["startDate"] = datetime.datetime.now().isoformat()

        assert isinstance(metadata, dict)
        for k, v in metadata.items():
            assert self.validate_fieldname(
                k
            ), f"{k} is not an accepted key in this dataset!"
            assert isinstance(
                v, str
            ), f"{v} is not an accepted value for ICAT (only strings are allowed)!"

        self._node.info["__closed__"] = False
        self._node.info.update(metadata)

        self._node.info["__metadata_gathered__"] = True

    @property
    def metadata_gathering_done(self):
        return self._node.info.get("__metadata_gathered__", False)

    def add_technique(self, technique):
        if self.is_closed:
            raise RuntimeError("The dataset is already closed")

        assert isinstance(technique, FieldGroup)
        self._node.info["__techniques__"] = self._node.techniques.union(
            [technique.name]
        )

    def write_metadata_field(self, fieldname, value):
        if self.is_closed:
            raise RuntimeError("The dataset is already closed")

        if value is None:
            if fieldname in self._node.info:
                self._node.info.pop(fieldname)
            return

        assert self.validate_fieldname(
            fieldname
        ), f"{fieldname} is not an accepted key in this dataset!"
        assert isinstance(
            value, str
        ), f"{value} is not an accepted value for ICAT (only strings are allowed)!"
        self._node.info[fieldname] = value

    def validate_fieldname(self, fieldname):
        return fieldname in self.definitions.all

    @property
    def missing_technique_fields(self):
        """returns a list of requiered metadata fields that
        are not yet filled"""
        return self.expected_technique_fields.difference(self.existing_fields)

    @property
    def techniques(self):
        """list of techniques used in this dataset"""
        # return [t.name for t in self._techniques]
        t = [
            self.definitions.techniques._asdict()[name]
            for name in self._node.techniques
        ]
        return t

    @property
    def expected_technique_fields(self):
        """all fields required by this dataset"""
        all_fields = set()
        for t in self.techniques:
            all_fields.update(t.fields)
        return all_fields

    @property
    def existing_fields(self):
        return set(self._node.metadata.keys())

    @autocomplete_property
    def expected(self):
        """namespace containing expected keys"""
        return CustomSetterNamespace(
            self.expected_technique_fields,
            self._node.info.get,
            self.write_metadata_field,
        )

    @autocomplete_property
    def existing(self):
        """namespace to access all existing keys"""
        return CustomSetterNamespace(
            self._node.metadata.keys(), self._node.info.get, self.write_metadata_field
        )

    @autocomplete_property
    def all(self):
        """namespace to access all possible keys"""
        return CustomSetterNamespace(
            self.definitions.all, self._node.info.get, self.write_metadata_field
        )

    # dict like access for scripts
    def __setitem__(self, key, value):
        self.write_metadata_field(key, value)

    def __getitem__(self, key):
        return self._node.info[key]

    def check_metatdata_consistency(self):
        mtf = self.missing_technique_fields
        if mtf:
            log_warning(
                self,
                f"The following metadata fields are expected by a given technique but not provided: {mtf}",
            )

    # todo make this a propery...
    def get_current_icat_metadata(self):
        return self._node.metadata

    def finalize_metadata(self):
        # check if a definiton is provided otherwhise use
        # names of application definition
        if "definition" not in self._node.metadata and len(self._node.techniques) != 0:
            self.write_metadata_field("definition", " ".join(self._node.techniques))

        self.write_metadata_field("endDate", datetime.datetime.now().isoformat())

    def close(self, icat_proxy):
        """Close the dataset in Redis and send to ICAT.
        The dataset will not be closed when it has no data on disk.

        :param IcatIngesterProxy icat_proxy:
        """
        if self.is_closed:
            raise RuntimeError("The dataset is already closed")
        if not self.has_data:
            # In the current implementation it is not possible
            # to close a dataset with scans but without data.
            self._log_debug("not closed because no data")
            return
        self.finalize_metadata()
        self._store_in_icat(icat_proxy)
        self._node.info["__closed__"] = True
        self._log_debug("closed dataset")

    def _store_in_icat(self, icat_proxy):
        """Only send to ICAT when the path exists

        :param IcatIngesterProxy icat_proxy:
        """
        self._log_debug("store in ICAT")
        sample = self.sample
        icat_proxy.store_dataset(
            sample.proposal.name,
            sample.name,
            self.name,
            self.path,
            metadata=self.get_current_icat_metadata(),
        )

    @property
    def sample(self):
        return Sample(self._node.parent)

    @property
    def proposal(self):
        return self.sample.proposal

    @property
    def scan_nodes(self):
        yield from self._node.children()

    @property
    def has_scans(self):
        try:
            next(self.scan_nodes)
        except StopIteration:
            return False
        else:
            return True

    @property
    def has_data(self):
        return os.path.exists(self.path)

    @property
    def is_closed(self):
        return self._node.is_closed
