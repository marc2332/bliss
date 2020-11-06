# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import os
import datetime
from bliss import current_session
from bliss.icat import FieldGroup
from bliss.common.utils import autocomplete_property
from bliss.icat.policy import DataPolicyObject
from bliss.icat.dataset_collection import DatasetCollection


class Dataset(DataPolicyObject):

    _REQUIRED_INFO = DataPolicyObject._REQUIRED_INFO | {"__closed__"}
    _NODE_TYPE = "dataset"

    def __init__(self, node):
        super().__init__(node)
        self._collection = None

    @property
    def expected_fields(self):
        """all fields required by this dataset"""
        all_fields = super().expected_fields
        # All technique fields are required
        for t in self.techniques:
            all_fields.update(t.fields)
        return all_fields

    def gather_metadata(self, on_exists=None):
        """Initialize the dataset node info.

        When metadata already exists in Redis:
            on_exists="skip": do nothing
            on_exists="overwrite": overwrite in Redis
            else: raise RuntimeError
        """
        if self.is_closed:
            raise RuntimeError("The dataset is already closed")

        if self.metadata_gathering_done:
            if on_exists == "skip":
                return
            elif on_exists == "overwrite":
                pass
            else:
                raise RuntimeError("Metadata gathering already done")

        # Gather metadata
        if current_session.icat_mapping:
            infodict = current_session.icat_mapping.get_metadata()
        else:
            infodict = dict()

        # Add additional metadata
        infodict["startDate"] = datetime.datetime.now().isoformat()

        # Check metadata
        for k, v in infodict.items():
            assert self.validate_fieldname(
                k
            ), f"{k} is not an accepted key in this dataset!"
            assert isinstance(
                v, str
            ), f"{v} is not an accepted value for ICAT (only strings are allowed)!"

        # Add other info keys (not metadata)
        infodict["__metadata_gathered__"] = True

        # Update the node's info
        self._node.info.update(infodict)

    @property
    def metadata_gathering_done(self):
        return self._node.info.get("__metadata_gathered__", False)

    def add_technique(self, technique):
        if self.is_closed:
            raise RuntimeError("The dataset is already closed")
        if isinstance(technique, FieldGroup):
            technique = technique.name
        available = self.definitions.techniques._fields
        if technique not in available:
            raise ValueError(f"Unknown technique ({available})")
        self._node.add_technique(technique)

    @property
    def techniques(self):
        """list of techniques used in this dataset"""
        tdict = self.definitions.techniques._asdict()
        return [tdict[name] for name in self._technique_names]

    @property
    def _technique_names(self):
        """list of technique names used in this dataset"""
        return self._node.techniques

    def finalize_metadata(self):
        # check if a definiton is provided otherwhise use
        # names of application definition
        if (
            not self.has_metadata_field("definition")
            and len(self._technique_names) != 0
        ):
            self.write_metadata_field("definition", " ".join(self._technique_names))

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
        self.freeze_inherited_icat_metadata()
        self._node.info["__closed__"] = True
        self._log_debug("closed dataset")

    def _store_in_icat(self, icat_proxy):
        """Only send to ICAT when the path exists

        :param IcatIngesterProxy icat_proxy:
        """
        self._log_debug("store in ICAT")
        collection = self.collection
        icat_proxy.store_dataset(
            collection.proposal.name,
            collection.name,
            self.name,
            self.path,
            metadata=self.get_current_icat_metadata(),
        )

    @autocomplete_property
    def collection(self):
        if self._collection is None:
            self._collection = DatasetCollection(self._node.parent)
        return self._collection

    @autocomplete_property
    def proposal(self):
        return self.collection.proposal

    @property
    def parent(self):
        return self.collection

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

    @autocomplete_property
    def description(self):
        # TODO: use Dataset_description when it gets introduced
        return self.get_metadata_field("Sample_description")

    @description.setter
    def description(self, value):
        # TODO: use Dataset_description when it gets introduced
        if value is not None:
            # TODO: remove this block when Dataset_description gets introduced
            sample_description = self.sample_description
            if sample_description:
                value = f"{sample_description} ({value})"
        self["Sample_description"] = value

    @autocomplete_property
    def sample_description(self):
        # TODO: use Dataset_description when it gets introduced
        return self.collection.sample_description

    @sample_description.setter
    def sample_description(self, value):
        # TODO: use Dataset_description when it gets introduced
        self.collection.sample_description = value

    @autocomplete_property
    def sample_name(self):
        return self.get_metadata_field("Sample_name")

    @sample_name.setter
    def sample_name(self, value):
        self["Sample_name"] = value
