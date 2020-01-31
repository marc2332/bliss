# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import getpass
import gevent
import os
import string
import time
import datetime
import tabulate
import uuid
import importlib

from bliss import current_session
from bliss.config.settings import ParametersWardrobe
from bliss.data.node import _get_or_create_node, _create_node, is_zerod
from bliss.data.scan import get_data
from bliss.scanning.writer.null import Writer as NullWriter
from bliss.scanning import writer as writer_module
from bliss.common.proxy import Proxy
from bliss.common.logtools import lprint
from bliss.common.tango import DeviceProxy, DevFailed

_SCAN_SAVING_CLASS = None

ScanSaving = Proxy(lambda: _SCAN_SAVING_CLASS or BasicScanSaving)


def set_scan_saving_class(klass):
    global _SCAN_SAVING_CLASS
    _SCAN_SAVING_CLASS = klass


class BasicScanSaving(ParametersWardrobe):
    DEFAULT_VALUES = {
        # default and not removable values
        "base_path": "/tmp/scans",
        "data_filename": "data",
        "user_name": getpass.getuser(),
        "template": "{session}/",
        "images_path_relative": True,
        "images_path_template": "scan{scan_number}",
        "images_prefix": "{img_acq_device}_",
        "date_format": "%Y%m%d",
        "scan_number_format": "%04d",
        "_writer_module": "hdf5",
    }
    # read only attributes implemented with python properties
    PROPERTY_ATTRIBUTES = [
        "session",
        "date",
        "scan_name",
        "scan_number",
        "img_acq_device",
        "writer",
    ]
    REDIS_SETTING_PREFIX = "scan_saving"

    def __init__(self, name=None):
        """
        This class hold the saving structure for a session.

        This class generate the *root path* of scans and the *parent* node use
        to publish data.

        The *root path* is generate using *base path* argument as the first part
        and use the *template* argument as the final part.

        The *template* argument is basically a (python) string format use to
        generate the final part of the root_path.

        i.e: a template like "{session}/{date}" will use the session and the date attribute
        of this class.

        Attribute used in this template can also be a function with one argument
        (scan_data) which return a string.

        i.e: date argument can point to this method
             def get_date(scan_data): datetime.datetime.now().strftime("%Y/%m/%d")
             scan_data.add('date',get_date)

        The *parent* node should be use as parameters for the Scan.
        """
        super().__init__(
            f"{self.REDIS_SETTING_PREFIX}:{name}"
            if name
            else f"{self.REDIS_SETTING_PREFIX}:{uuid.uuid4().hex}",
            default_values=self.DEFAULT_VALUES,
            property_attributes=self.PROPERTY_ATTRIBUTES,
            not_removable=self.DEFAULT_VALUES.keys(),
        )

    def __dir__(self):
        keys = super().__dir__()
        return keys + ["get", "get_path", "get_parent_node"] + PROPERTY_ATTRIBUTES

    def __info__(self):
        d = self._get_instance(self.current_instance)
        d["scan_name"] = "scan name"
        d["scan_number"] = "scan number"
        d["img_acq_device"] = "<images_* only> acquisition device name"

        info_str = super()._repr(d)
        info_str += self.get_data_info()

        return info_str

    def get_data_info(self):
        writer = self.get_writer_object()
        info_table = list()
        if isinstance(writer, NullWriter):
            info_table.append(("NO SAVING",))
        else:
            writer.template.update(
                {
                    "scan_name": "{scan_name}",
                    "session": self.session,
                    "scan_number": "{scan_number}",
                }
            )
            data_file = writer.filename
            data_dir = os.path.dirname(data_file)

            if os.path.exists(data_file):
                exists = "exists"
            else:
                exists = "does not exist"
            info_table.append((exists, "filename", data_file))

            if os.path.exists(data_dir):
                exists = "exists"
            else:
                exists = "does not exist"
            info_table.append((exists, "root_path", data_dir))

        return tabulate.tabulate(tuple(info_table))

    @property
    def scan_name(self):
        return "{scan_name}"

    @property
    def scan_number(self):
        return "{scan_number}"

    @property
    def img_acq_device(self):
        return "{img_acq_device}"

    @property
    def session(self):
        """ This give the name of the current session or 'default' if no current session is defined """
        return current_session.name

    @property
    def date(self):
        return time.strftime(self.date_format)

    @property
    def writer(self):
        """
        Scan writer object.
        """
        return self._writer_module

    @writer.setter
    def writer(self, value):
        try:
            if value is not None:
                self._get_writer_class(value)
        except ImportError as exc:
            raise ImportError(
                "Writer module **%s** does not"
                " exist or cannot be loaded (%s)"
                " possible module are %s" % (value, exc, writer_module.__all__)
            )
        except AttributeError as exc:
            raise AttributeError(
                "Writer module **%s** does have"
                " class named Writer (%s)" % (value, exc)
            )
        else:
            self._writer_module = value

    def _format(self, template_string, cache_dict):
        """Format the template string using object user attributes and properties,
        return both the result string and the values dict

        Functions are called to get the string value
        """
        formatter = string.Formatter()
        template_keys = [key[1] for key in formatter.parse(template_string)]

        for key in template_keys:
            value = cache_dict.get(key)
            if callable(value):
                value = value(self)  # call the function
                cache_dict[key] = value

        return template_string.format(**cache_dict)

    def _get_path(self):
        """
        This method return the current saving path and data filename
        The path is compute with *base_path* and follow the *template* attribute
        to generate it.
        """
        data_filename = self.data_filename
        template = os.path.join(self.base_path, self.template)
        cache_dict = self.to_dict(export_properties=True)
        path = os.path.normpath(self._format(template, cache_dict))

        images_template = self.images_path_template
        images_prefix = self.images_prefix
        images_sub_path = images_template.format(**cache_dict)
        images_prefix = images_prefix.format(**cache_dict)
        if self.images_path_relative:
            images_path = os.path.join(path, images_sub_path, images_prefix)
        else:
            images_path = os.path.join(images_sub_path, images_prefix)

        return path, images_path, data_filename.format(**cache_dict)

    def get_path(self):
        return self._get_path()[0]

    def get(self):
        """
        This method will compute all configurations needed for a new acquisition.
        It will return a dictionary with:
            root_path -- compute root path with *base_path* and *template* attribute
            images_path -- compute images path with *base_path* and *images_path_template* attribute
                If images_path_relative is set to True (default), the path
                template is relative to the scan path, otherwise the
                image_path_template has to be an absolute path.
            parent -- DataNodeContainer to be used as a parent for new acquisition
        """
        root_path, images_path, data_filename = self._get_path()

        db_path_items = [(self.session, "container")]
        path_items = list(filter(None, root_path.split(os.path.sep)))
        for path_item in path_items:
            db_path_items.append((path_item, "container"))

        return {
            "root_path": root_path,
            "data_path": os.path.join(root_path, data_filename),
            "images_path": images_path,
            "db_path_items": db_path_items,
            "writer": self.get_writer_object(
                paths=(root_path, images_path, data_filename)
            ),
        }

    def get_writer_object(self, paths=None):
        if self.writer is None:
            return
        if paths:
            root_path, images_path, data_filename = paths
        else:
            root_path, images_path, data_filename = self._get_path()
        klass = self._get_writer_class(self.writer)
        return klass(root_path, images_path, data_filename)

    def get_parent_node(self):
        """
        This method return the parent node which should be used to publish new data
        """
        db_path_items = self.get()["db_path_items"]
        parent_node = _get_or_create_node(*db_path_items[0])
        for item_name, node_type in db_path_items[1:]:
            parent_node = _get_or_create_node(item_name, node_type, parent=parent_node)
        return parent_node

    def _get_writer_class(self, writer_module_name):
        module_name = f"{writer_module.__name__}.{writer_module_name}"
        module = importlib.import_module(module_name)
        return getattr(module, "Writer")


class ESRFScanSaving(BasicScanSaving):
    DEFAULT_VALUES = {
        # default and not removable values
        "user_name": getpass.getuser(),
        "template": "",
        "images_path_template": "scan{scan_number}",
        "images_prefix": "{img_acq_device}_",
        "date_format": "%Y%m%d",
        "scan_number_format": "%04d",
        "_writer_module": "nexus",
        "_proposal": "",
        "_sample": "",
        "_dataset": "",
    }
    PROPERTY_ATTRIBUTES = BasicScanSaving.PROPERTY_ATTRIBUTES + [
        "beamline",
        "base_path",
        "data_root",
        "data_filename",
        "proposal",
        "sample",
        "dataset",
        "images_path_relative",
    ]
    REDIS_SETTING_PREFIX = "esrf_scan_saving"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    @property
    def scan_saving_config(self):
        return current_session.config.root.get("scan_saving", {})

    @property
    def images_path_relative(self):
        # this is not an option
        return True

    @property
    def beamline(self):
        bl = self.scan_saving_config["beamline"]
        if bl is None:
            return os.environ.get("BEAMLINENAME")
        return bl.lower()

    @property
    def base_path(self):
        return os.path.join(
            self.data_root, "{proposal}/{beamline}/{sample}/{sample}_{dataset}"
        )

    @property
    def data_root(self):
        for proposal_prefix in ("blc", "ih", self.beamline):
            if self.proposal.lower().startswith(proposal_prefix):
                inhouse_root = self.scan_saving_config.get(
                    "inhouse_data_root", "/data/{beamline}/inhouse"
                )
                return inhouse_root.format(**{"beamline": self.beamline})
        return self.scan_saving_config.get("visitor_data_root", "/data/visitor")

    @property
    def data_filename(self):
        # file extension is set by nexus writer
        return "{sample}_{dataset}"

    @property
    def proposal(self):
        if not self._proposal:
            yymm = time.strftime("%y%m")
            self._proposal = f"{self.beamline}{yymm}"
        return self._proposal

    @proposal.setter
    def proposal(self, value):
        self._proposal = value

    @property
    def sample(self):
        if not self._sample:
            self._sample = "default"
        return self._sample

    @sample.setter
    def sample(self, value):
        self._sample = value

    def _check_dataset_path(self, dataset_to_check):
        template = os.path.join(
            self.base_path, self.template, self.data_filename + ".h5"
        )
        cache_dict = self.to_dict(export_properties=False)
        cache_dict.update(
            {
                prop: getattr(self, prop)
                for prop in self.PROPERTY_ATTRIBUTES
                if prop != "dataset"
            }
        )
        cache_dict["dataset"] = "%(dataset)s"
        path = self._format(template, cache_dict) % {"dataset": dataset_to_check}
        if os.path.exists(os.path.dirname(path)) or os.path.exists(path):
            return False
        return True

    @property
    def dataset(self):
        if not self._dataset:
            self.dataset = ""
        return self._dataset

    @dataset.setter
    def dataset(self, value):
        if value:
            if self._check_dataset_path(value):
                self._dataset = value
                return
            else:
                value += "_"
                start = 2
        else:
            value = ""
            start = 1
        dataset_template = f"{value}%04d"
        for i in range(start, 1000):
            dataset_name = dataset_template % i
            if self._check_dataset_path(dataset_name):
                self._dataset = dataset_name
                return
        raise ValueError("Cannot set dataset: cannot overwrite existing file path")

