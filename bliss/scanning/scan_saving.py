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
import tabulate
import uuid
import importlib
import re
import itertools
import traceback
from functools import wraps
import logging

from bliss import current_session
from bliss.config.settings import ParametersWardrobe
from bliss.data.node import _get_or_create_node
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


logger = logging.getLogger(__name__)


class MissingParameter(ValueError):
    pass


class CircularReference(ValueError):
    pass


def eval_wraps(method):
    """Like `functools.wraps` but adding a prefix
    "_with_eval_dict_" to the method `__name__`.

    :param callable method: unbound method of a class
    :returns callable:
    """

    def wrap(wrapper):
        wrapper = wraps(method)(wrapper)
        wrapper.__name__ = "_with_eval_dict_" + wrapper.__name__
        return wrapper

    return wrap


def with_eval_dict(method):
    """This passes a dictionary as named argument `eval_dict` to the method
    when it is not passed by the caller. This dictionary is used for caching
    parameter evaluations (user attributes and properties) in `EvalParametersWardrobe`.

    :param callable method: unbound method of `EvalParametersWardrobe`
    :returns callable:
    """
    return with_config_eval_dict()(method)


def with_config_eval_dict(**eval_config):
    """Like `with_eval_dict` but with configurable parameter
    evaluation caching.

    :param eval_config: use to control what parameters are cached
                        (named arguments for the `_eval_dict` method)
    :returns callable:
    """

    def wrap(method):
        @eval_wraps(method)
        def eval_func(self, *args, **kwargs):
            # Create a cache dictionary if not provided by caller
            if "eval_dict" in kwargs:
                eval_dict = kwargs.get("eval_dict")
            else:
                eval_dict = None
            if eval_dict is None:
                logger.debug(
                    "create eval_dict (method {})".format(repr(method.__name__))
                )
                # Survives only for the duration of the call
                eval_dict = kwargs["eval_dict"] = {}
            if not eval_dict:
                self._update_eval_dict(eval_dict, **eval_config)
                logger.debug(
                    "filled eval_dict (method {})".format(repr(method.__name__))
                )
            # Evaluate method (passes eval_dict)
            return method(self, *args, **kwargs)

        return eval_func

    return wrap


def property_with_eval_dict(getter):
    """Combine the `with_eval_dict` and `property` decorators

    :param callable getter: unbound method of a class
    :returns callable:
    """
    return property(with_eval_dict(getter))


def property_with_config_eval_dict(**eval_config):
    """Like `property_with_eval_dict` but with configurable
    caching of parameter evaluation.

    :param eval_config: control what parameters are cached
                        (named arguments for the `_update_eval_dict` method)
    :returns callable:
    """

    def wrap(getter):
        return property(with_config_eval_dict(**eval_config)(getter))

    return wrap


def is_circular_call(funcname):
    """Check whether a function is called recursively

    :param str funcname:
    :returns bool:
    """
    # This is good enough for our purpose
    return any(f.name == funcname for f in traceback.extract_stack())


class EvalParametersWardrobe(ParametersWardrobe):
    """A parameter value in the Wardrobe can be:

        - literal string: do nothing
        - template string: fill with other parameters (recursive)
        - callable: unbound method of this class with signature
                    `method(self)` or `method(self, eval_dict=...)`
        - other: converted to string

    Methods with the `with_eval_dict` decorator will cache the evaluation
    of these parameter values (user attributes and properties).

    Properties with the `with_eval_dict` decorator need to be called with
    `get_cached_property` or `set_cached_property` to pass the cache dictionary.
    When used as a normal property, a temporary cache dictionary is created.

    The evaluation cache is shared by recursive calls (passed as an argument).
    It is not persistant unless you pass it explicitely as an argument on the
    first call to a `with_eval_dict` decorated method.

    Parameter evaluation is done with the method `eval_template`, which can
    also be used externally to evaluate any string template that contains
    wardrobe parameter fields.
    """

    FORMATTER = string.Formatter()

    def _template_named_fields(self, template):
        """Get all the named fields in a template.
        For example "a{}bc{d}efg{h}ij{:04d}k" has two named fields.

        :pram str template:
        :returns set(str):
        """
        return {
            fieldname
            for _, fieldname, _, _ in self.FORMATTER.parse(template)
            if fieldname is not None
        }

    @with_eval_dict
    def eval_template(self, template, eval_dict=None):
        """Equivalent to `template.format(**eval_dict)` with additional properties:
            - The values in `eval_dict` can be callable or template strings themselves.
            - They will be evaluated recursively and replaced in `eval_dict`.

        :param str or callable template:
        :param dict eval_dict:
        """
        eval_dict.setdefault("__evaluated__", set())

        # Evaluate callable and throw exception on empty value
        if callable(template):
            try:
                template = template(self, eval_dict=eval_dict)
            except TypeError:
                template = template(self)
            if template is None:
                raise MissingParameter("Parameters value generator returned `None`")
            if not isinstance(template, str):
                template = str(template)
        else:
            if template is None:
                raise MissingParameter
            if not isinstance(template, str):
                template = str(template)

        # Evaluate fields that have not been evaluated yet
        fields = self._template_named_fields(template)
        already_evaluated = eval_dict["__evaluated__"].copy()
        eval_dict["__evaluated__"] |= fields
        for field in fields - already_evaluated:
            value = eval_dict.get(field)
            try:
                eval_dict[field] = self.eval_template(value, eval_dict=eval_dict)
            except MissingParameter:
                raise MissingParameter("Parameter {} is missing".format(repr(field)))

        # Evaluate string template while avoiding circular references
        fill_dict = {}
        for field in fields:
            value = eval_dict[field]
            ffield = "{{{}}}".format(field)
            if ffield in value:
                # Stop evaluating circular reference
                # raise CircularReference("Parameter {} contains a circular reference".format(repr(field)))
                fill_dict[field] = ffield
            else:
                fill_dict[field] = value
        return template.format(**fill_dict)

    def _update_eval_dict(self, eval_dict, **replace_properties):
        """Update the evaluation dictionary with user attributes (from Redis)
        and properties when missing.

        :param dict eval_dict:
        :param replace_properties: avoid calling the getters of these properties
                                   property is skipped when `None`
        :returns dict:
        """
        fromredis = self.to_dict(export_properties=False)
        for k, v in fromredis.items():
            if k not in eval_dict:
                eval_dict[k] = v
        for prop in self._property_attributes:
            if prop in eval_dict:
                continue
            if prop in replace_properties:
                # Skip or replace property
                value = replace_properties[prop]
                if value is not None:
                    eval_dict[prop] = value
            else:
                self.get_cached_property(prop, eval_dict)

    def get_cached_property(self, name, eval_dict):
        """Pass `eval_dict` to a property getter. If the property has
        already been evaluated before (meaning it is in `eval_dict`)
        then that value will be used without calling the property getter.

        :param str name: property name
        :param dict eval_dict:
        :returns any:
        """
        if name in eval_dict:
            return eval_dict[name]
        _prop = getattr(self.__class__, name)
        try:
            fget = _prop.fget
        except AttributeError:
            # Not a property
            r = getattr(self, name)
        else:
            # See eval_wraps
            cname = "_with_eval_dict_" + name
            if fget.__name__ == cname:
                logger.debug("fget eval property " + repr(name))
                if is_circular_call(cname):
                    raise CircularReference(
                        "Property {} contains a circular reference".format(repr(name))
                    )
                r = fget(self, eval_dict=eval_dict)
            else:
                logger.debug("fget normal property " + repr(name))
                r = fget(self)
        eval_dict[name] = r
        return r

    def set_cached_property(self, name, value, eval_dict):
        """Pass `eval_dict` to a property setter.

        :param str name: property name
        :param any value:
        :param dict eval_dict:
        """
        _prop = getattr(self.__class__, name)
        try:
            fset = _prop.fset
        except AttributeError:
            # Not a property
            setattr(self, name, value)
        else:
            # See `eval_wraps`
            cname = "_with_eval_dict_" + name
            if fset.__name__ == cname:
                logger.debug("fset eval property " + repr(name))
                if is_circular_call(cname):
                    raise CircularReference(
                        "Property {} contains a circular reference".format(repr(name))
                    )
                fset(self, value, eval_dict=eval_dict)
            else:
                logger.debug("fset normal property " + repr(name))
                fset(self, value)
        eval_dict[name] = value


class BasicScanSaving(EvalParametersWardrobe):
    """Parameterized representation of the scan data file path

        base_path/template/data_filename+file_extension

    where each part (except for the file extension) is generated
    from user attributes and properties.
    """

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
        # saved properties in Redis:
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
        "data_policy",
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
        return (
            keys
            + [
                "get",
                "get_path",
                "get_parent_node",
                "filename",
                "root_path",
                "images_path",
            ]
            + self.PROPERTY_ATTRIBUTES
        )

    def __info__(self):
        d = {}
        self._update_eval_dict(d)
        d["img_acq_device"] = "<images_* only> acquisition device name"
        info_str = super()._repr(d)
        extra = self.get_data_info(eval_dict=d)
        info_str += tabulate.tabulate(tuple(extra))
        return info_str

    @with_eval_dict
    def get_data_info(self, eval_dict=None):
        """
        :returns list:
        """
        writer = self.get_cached_property("writer_object", eval_dict)
        info_table = list()
        if isinstance(writer, NullWriter):
            info_table.append(("NO SAVING",))
        else:
            data_file = writer.filename
            data_dir = os.path.dirname(data_file)

            if os.path.exists(data_file):
                label = "exists"
            else:
                label = "does not exist"
            info_table.append((label, "filename", data_file))

            if os.path.exists(data_dir):
                label = "exists"
            else:
                label = "does not exist"
            info_table.append((label, "directory", data_dir))

        return info_table

    @property
    def scan_name(self):
        return "{scan_name}"

    @property
    def scan_number(self):
        return "{scan_number}"

    @property
    def data_policy(self):
        return "None"

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

    def get_path(self):
        return self.root_path

    @property_with_eval_dict
    def root_path(self, eval_dict=None):
        """Directory of the scan *data file*
        """
        base_path = self.get_cached_property("base_path", eval_dict)
        template = os.path.join(base_path, self.template)
        return os.path.abspath(self.eval_template(template, eval_dict=eval_dict))

    @property_with_eval_dict
    def data_path(self, eval_dict=None):
        """Full path for the scan *data file* without the extension
        This is before the writer modifies the name (given by `self.filename`)
        """
        root_path = self.get_cached_property("root_path", eval_dict)
        data_filename = self.get_cached_property("eval_data_filename", eval_dict)
        return os.path.join(root_path, data_filename)

    @property_with_eval_dict
    def data_fullpath(self, eval_dict=None):
        """Full path for the scan *data file* with the extension.
        This is before the writer modifies the name (given by `self.filename`)
        """
        data_path = self.get_cached_property("data_path", eval_dict)
        unknowns = self._template_named_fields(data_path)
        data_path = data_path.format(**{f: "{" + f + "}" for f in unknowns})
        return os.path.extsep.join((data_path, self.file_extension))

    @property_with_eval_dict
    def eval_data_filename(self, eval_dict=None):
        """The evaluated version of data_filename
        """
        return self.eval_template(self.data_filename, eval_dict=eval_dict)

    @property_with_eval_dict
    def filename(self, eval_dict=None):
        """Full path for the scan *data file* with the extension.
        Could be modified by the writer instance.
        """
        return self.get_cached_property("writer_object", eval_dict).filename

    @property_with_eval_dict
    def images_path(self, eval_dict=None):
        """Path to be used by external devices (normally a string template)
        """
        images_template = self.images_path_template
        images_prefix = self.images_prefix
        images_sub_path = self.eval_template(images_template, eval_dict=eval_dict)
        images_prefix = self.eval_template(images_prefix, eval_dict=eval_dict)
        if self.images_path_relative:
            root_path = self.get_cached_property("root_path", eval_dict)
            return os.path.join(root_path, images_sub_path, images_prefix)
        else:
            return os.path.join(images_sub_path, images_prefix)

    @with_eval_dict
    def get(self, eval_dict=None):
        """
        This method will compute all configurations needed for a new scan.
        It will return a dictionary with:
            root_path -- compute root path with *base_path* and *template* attribute
            images_path -- compute images path with *base_path* and *images_path_template* attribute
                If images_path_relative is set to True (default), the path
                template is relative to the scan path, otherwise the
                images_path_template has to be an absolute path.
            db_path_items -- information needed to create the parent node in Redis for the new scan
            writer -- a writer instance
        """
        return {
            "root_path": self.get_cached_property("root_path", eval_dict),
            "data_path": self.get_cached_property("data_path", eval_dict),
            "images_path": self.get_cached_property("images_path", eval_dict),
            "db_path_items": self.get_cached_property("_db_path_items", eval_dict),
            "writer": self.get_cached_property("writer_object", eval_dict),
        }

    @property_with_eval_dict
    def scan_parent_db_name(self, eval_dict=None):
        """The Redis name of a scan's parent node is a concatenation of session
        name and data directory (e.g. "session_name:tmp:scans")
        """
        return ":".join(self.get_cached_property("_db_path_keys", eval_dict))

    @property_with_eval_dict
    def _db_path_keys(self, eval_dict=None):
        """The Redis name of a scan's parent node is a concatenation of session
        name and data directory (e.g. ["session_name", "tmp", "scans"])

        Duplicate occurences of "session_name" are removed.

        :returns list(str):
        """
        session = self.session
        parts = self.get_cached_property("root_path", eval_dict).split(os.path.sep)
        return [session] + [p for p in parts if p and p != session]

    @property_with_eval_dict
    def _db_path_items(self, eval_dict=None):
        """For scan's parent node creation (see `get_parent_node`)

        :returns list(tuple):
        """
        parts = self.get_cached_property("_db_path_keys", eval_dict)
        return list(zip(parts, ["container"] * len(parts)))

    @property_with_eval_dict
    def writer_object(self, eval_dict=None):
        """This instantiates the writer class

        :returns bliss.scanning.writer.File:
        """
        root_path = self.get_cached_property("root_path", eval_dict)
        images_path = self.get_cached_property("images_path", eval_dict)
        data_filename = self.get_cached_property("eval_data_filename", eval_dict)
        klass = self._get_writer_class(self.writer)
        writer = klass(root_path, images_path, data_filename)
        s = root_path + images_path + data_filename
        writer.template.update(
            {f: "{" + f + "}" for f in self._template_named_fields(s)}
        )
        return writer

    @property
    def file_extension(self):
        """As determined by the writer
        """
        return self._get_writer_class(self.writer).FILE_EXTENSION

    def get_writer_object(self):
        """This instantiates the writer class
        :returns bliss.scanning.writer.File:
        """
        return self.writer_object

    def create_path(self, path):
        """The path is created by the writer if the path if part
        of the data root, else by Bliss (subdir or outside data root).

        :param str path:
        """
        self.writer_object.create_path(os.path.abspath(path))

    def create_root_path(self):
        """Create the scan data directory
        """
        self.create_path(self.root_path)

    def get_parent_node(self):
        """
        This method return the parent node which should be used to publish new data
        """
        db_path_items = self._db_path_items
        parent_node = None
        for item_name, node_type in db_path_items:
            parent_node = _get_or_create_node(item_name, node_type, parent=parent_node)
        return parent_node

    def _get_writer_class(self, writer_module_name):
        module_name = f"{writer_module.__name__}.{writer_module_name}"
        module = importlib.import_module(module_name)
        return getattr(module, "Writer")

    def newproposal(self, proposal_name):
        raise NotImplementedError("No data policy enabled")

    def newsample(self, sample_name):
        raise NotImplementedError("No data policy enabled")

    def newdataset(self, dataset_name):
        raise NotImplementedError("No data policy enabled")


class ESRFScanSaving(BasicScanSaving):
    """Parameterized representation of the scan data file path
    according to the ESRF data policy

        base_path/template/data_filename+file_extension

    where the base_path is determined by the proposal name,
    the template is fixed to "{proposal}/{beamline}/{sample}/{sample}_{dataset}"
    and the data_filename is fixed to "{sample}_{dataset}".
    """

    DEFAULT_VALUES = {
        # default and not removable values
        "user_name": getpass.getuser(),
        "images_path_template": "scan{scan_number}",
        "images_prefix": "{img_acq_device}_",
        "date_format": "%Y%m%d",
        "scan_number_format": "%04d",
        "dataset_number_format": "%04d",
        "technique": "",
        # saved properties in Redis:
        "_writer_module": "nexus",
        "_proposal": "",
        "_sample": "",
        "_dataset": "",
    }
    # Order imported for resolving dependencies
    PROPERTY_ATTRIBUTES = BasicScanSaving.PROPERTY_ATTRIBUTES + [
        "template",
        "beamline",
        "proposal",
        "base_path",
        "sample",
        "dataset",
        "data_filename",
        "images_path_relative",
    ]
    REDIS_SETTING_PREFIX = "esrf_scan_saving"
    SLOTS = ["_tango_metadata_manager", "_tango_metadata_experiment"]
    ICAT_STATUS = {
        "OFF": "No experiment ongoing",
        "STANDBY": "Experiment started, sample or dataset not specified",
        "ON": "No dataset running",
        "RUNNING": "Dataset is running",
        "FAULT": "Device is not functioning correctly",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._tango_metadata_manager = None
        self._tango_metadata_experiment = None

    @property
    def data_policy(self):
        return "ESRF"

    @with_eval_dict
    def get_data_info(self, eval_dict=None):
        """
        :returns list:
        """
        info_table = super().get_data_info(eval_dict=eval_dict)
        try:
            icat_state = self.icat_state
            icat_status = self.icat_status
        except DevFailed:
            if not os.environ.get("TANGO_HOST"):
                icat_state = "no TANGO_HOST defined"
                icat_status = ""
            else:
                icat_state = "unknown"
                icat_status = ""
        info_table.append(("Metadata", icat_state, icat_status))
        return info_table

    @property
    def scan_saving_config(self):
        return current_session.config.root.get("scan_saving", {})

    @property
    def images_path_relative(self):
        # Always relative due to the data policy
        return True

    @property
    def beamline(self):
        bl = self.scan_saving_config.get("beamline")
        if not bl:
            return "{beamline}"
        # Alphanumeric, space, dash and underscore
        if not re.match(r"^[0-9a-zA-Z_\s\-]+$", bl):
            raise ValueError("Beamline name is invalid")
        return re.sub(r"[^0-9a-z]", "", bl.lower())

    @property
    def template(self):
        return "{proposal}/{beamline}/{sample}/{sample}_{dataset}"

    @property_with_eval_dict
    def base_path(self, eval_dict=None):
        """Root directory depending in the proposal type (inhouse, visitor, tmp)
        """
        ptype = self.get_cached_property("proposal_type", eval_dict)
        if ptype == "inhouse":
            base_path = self.scan_saving_config.get(
                "inhouse_data_root", "/data/{beamline}/inhouse"
            )
        elif ptype == "visitor":
            base_path = self.scan_saving_config.get(
                "visitor_data_root", "/data/visitor"
            )
        else:
            base_path = self.scan_saving_config.get(
                "tmp_data_root", "/data/{beamline}/tmp"
            )
        return self.eval_template(base_path, eval_dict=eval_dict)

    @property
    def data_filename(self):
        """File name template without extension
        """
        return "{sample}_{dataset}"

    @property_with_eval_dict
    def proposal(self, eval_dict=None):
        if not self._proposal:
            yymm = time.strftime("%y%m")
            self._proposal = f"{{beamline}}{yymm}"
        return self.eval_template(self._proposal, eval_dict=eval_dict)

    @proposal.setter
    def proposal(self, value):
        if value:
            # Alphanumeric, space, dash and underscore
            if not re.match(r"^[0-9a-zA-Z_\s\-]+$", value):
                raise ValueError("Proposal name is invalid")
            value = value.lower()
            value = re.sub(r"[^0-9a-z]", "", value)
        self._proposal = value

    @property_with_eval_dict
    def proposal_type(self, eval_dict=None):
        proposal = self.get_cached_property("proposal", eval_dict)
        bl = self.get_cached_property("beamline", eval_dict)
        for proposal_prefix in ("blc", "ih", bl):
            if proposal.startswith(proposal_prefix):
                return "inhouse"
        for proposal_prefix in ("tmp", "temp", "test"):
            if proposal.startswith(proposal_prefix):
                return "tmp"
        return "visitor"

    @property
    def sample(self):
        if not self._sample:
            self._sample = "sample"
        return self._sample

    @sample.setter
    def sample(self, value):
        if value:
            # Alphanumeric, space, dash and underscore
            if not re.match(r"^[0-9a-zA-Z_\s\-]+$", value):
                raise ValueError("Sample name is invalid")
            value = re.sub(r"[_\s\-]+", "_", value.strip())
        self._sample = value

    @property_with_eval_dict
    def dataset(self, eval_dict=None):
        if not self._dataset:
            self.set_cached_property("dataset", "", eval_dict)
        return self._dataset

    @dataset.setter
    @with_eval_dict
    def dataset(self, value, eval_dict=None):
        """
        :param int or str value:
        """
        for dataset_name in self._dataset_name_generator(value):
            if not self._dataset_exists(dataset_name, eval_dict=eval_dict):
                self._dataset = eval_dict["dataset"] = dataset_name
                eval_dict.pop("root_path", None)
                eval_dict.pop("data_path", None)
                eval_dict.pop("data_fullpath", None)
                return

    def _dataset_exists(self, dataset_name, eval_dict):
        # TODO: check existance with ICAT database instead?
        eval_dict.pop("root_path", None)
        eval_dict.pop("data_path", None)
        eval_dict.pop("data_fullpath", None)
        eval_dict["dataset"] = dataset_name
        # TODO: what should be used?
        # data directory:
        path = self.get_cached_property("root_path", eval_dict)
        # theoretical full path:
        # path = self.get_cached_property("data_fullpath", eval_dict)
        # full path as given by the writer instance:
        # path = self.get_cached_property("filename", eval_dict)
        return os.path.exists(path)

    def _dataset_name_generator(self, prefix):
        """Generates dataset names

        When prefix is a number (provided as int or str):
        "0005", "0006", ...

        Without prefix:
        "0001", "0002", ...

        All other cases:
        "prefix", "prefix_0002", "prefix_0003", ...

        :param int or str prefix:
        :yields str:
        """
        # Prefix and start index
        start = 0
        if prefix:
            if isinstance(prefix, str):
                if prefix.isdigit():
                    start = int(prefix)
                    prefix = ""
                else:
                    # Alphanumeric, space, dash and underscore
                    if not re.match(r"^[0-9a-zA-Z_\s\-]+$", prefix):
                        raise ValueError("Dataset name is invalid")
                    prefix = re.sub(r"[_\s\-]+", "_", prefix.strip())
            else:
                start = int(prefix)
                prefix = ""
        else:
            prefix = ""
        # Yield the prefix as first name
        if prefix:
            start = max(start, 2)
            yield prefix
        else:
            start = max(start, 1)
        # Yield consecutive names
        if prefix:
            template = f"{prefix}_{self.dataset_number_format}"
        else:
            template = f"{self.dataset_number_format}"
        for i in itertools.count(start):
            yield template % i
            gevent.sleep()

    @with_eval_dict
    def get(self, eval_dict=None):
        """Synchronizes the saving parameters with ICAT which may involve
        changing the ICAT dataset. This method is NOT always idempotent.
        """
        saving_dict = super().get(eval_dict=eval_dict)
        self.icat_sync(eval_dict=eval_dict)
        return saving_dict

    @property
    def metadata_manager(self):
        """Manages the dataset (data and metadata ingestion).
        Different techniques with different metadata will be served
        by different metadata managers.
        """
        if self._tango_metadata_manager is None:
            self._tango_metadata_manager = DeviceProxy(
                f"{self.beamline}/metadata/{self.session}"
            )
        return self._tango_metadata_manager

    @property
    def icat_state(self):
        return str(self.metadata_manager.state())

    @property
    def icat_status(self):
        return self.ICAT_STATUS[self.icat_state]

    @property
    def metadata_experiment(self):
        """Manages the sample and proposal (for all techniques).
        """
        if self._tango_metadata_experiment is None:
            self._tango_metadata_experiment = DeviceProxy(
                f"{self.beamline}/metaexp/{self.session}"
            )
        return self._tango_metadata_experiment

    @with_eval_dict
    def icat_sync(self, eval_dict=None):
        """Synchronize scan saving parameters with ICAT (push).
        When a dataset with different parameters is already running,
        is is stopped (meaning its data and metadata are ingested by ICAT).

        When no exception is raised, the possible ICAT states after
        synchronization are ON or FAULT.

        This method is NOT always idempotent.

        :raises RuntimeError: ICAT state exception
        :raises DevFailed: communication or server-side exception
        """
        root_path = self.get_cached_property("root_path", eval_dict)
        beamline = self.get_cached_property("beamline", eval_dict)
        response = self.metadata_experiment.get_property("beamlineID")
        if beamline != response.get("beamlineID", [""])[0]:
            self.metadata_experiment.put_property({"beamlineID": [beamline]})
        proposal = self.get_cached_property("proposal", eval_dict)
        if proposal != self.metadata_experiment.proposal:
            self._icat_set_proposal(proposal, root_path)
        sample = self.sample
        if sample != self.metadata_experiment.sample:
            self._icat_set_sample(sample)
        dataset = self.get_cached_property("dataset", eval_dict)
        if dataset != self.metadata_manager.datasetName:
            self._icat_set_dataset(dataset)
        self._icat_ensure_running()

    def _icat_ensure_notrunning(self, timeout=3):
        """Make sure the ICAT dataset is not running. Does not wait for the server to finish.
        When stopping a running dataset, data and metadata is ingested by the ICAT servers.

        :param num timeout:
        :raises RuntimeError: cannot stop the ICAT dataset
        :raises DevFailed: communication or server-side exception
        """
        if self.icat_state == "RUNNING":
            self.metadata_manager.endDataset()
            # Dataset name is reset by the server
        self._icat_wait_until_not_state(
            ["RUNNING"], "Failed to stop the running ICAT dataset"
        )

    def _icat_ensure_running(self, timeout=3):
        """Make sure the ICAT dataset is running.

        :param num timeout:
        :raises RuntimeError: cannot start the ICAT dataset
        :raises DevFailed: communication or server-side exception
        """
        if self.icat_state != "RUNNING":
            self._icat_wait_until_state(
                ["ON"], "Cannot start the ICAT dataset (sample or dataset not defined)"
            )
            self.metadata_manager.startDataset()
            self._icat_wait_until_state(["RUNNING"], "Failed to start the ICAT dataset")

    def _icat_wait_until_state(self, states, timeoutmsg="", timeout=3):
        """
        :param list(str) states:
        :param num timeout:
        :raises RuntimeError: timeout
        """
        try:
            with gevent.Timeout(timeout):
                while self.icat_state not in states:
                    gevent.sleep(0.1)
        except gevent.Timeout:
            if timeoutmsg:
                timeoutmsg = f"{timeoutmsg} ({self.icat_status})"
            else:
                timeoutmsg = repr(self.icat_status)
            raise RuntimeError(timeoutmsg)

    def _icat_wait_until_not_state(self, states, timeoutmsg="", timeout=3):
        """
        :param list(str) states:
        :param num timeout:
        :raises RuntimeError: timeout
        """
        try:
            with gevent.Timeout(timeout):
                while self.icat_state in states:
                    gevent.sleep(0.1)
        except gevent.Timeout:
            if timeoutmsg:
                timeoutmsg = f"{timeoutmsg} ({self.icat_status})"
            else:
                timeoutmsg = repr(self.icat_status)
            raise RuntimeError(timeoutmsg)

    def _icat_set_proposal(self, proposal, root_path, timeout=3):
        """
        :param str proposal:
        :param str root_path:
        :param num timeout:
        :raises RuntimeError: timeout
        """
        exception = None
        try:
            with gevent.Timeout(timeout):
                timeoutmsg = "Failed to stop the running ICAT dataset"
                self._icat_ensure_notrunning(timeout=None)
                timeoutmsg = "Failed to set the ICAT proposal name"
                while True:
                    try:
                        self.metadata_experiment.proposal = proposal
                        self.metadata_experiment.dataRoot = root_path
                        # Clears sample and dataset name in ICAT servers
                    except Exception as e:
                        exception = e
                        if self.icat_state == "OFF":
                            gevent.sleep(0.1)
                        else:
                            raise
                    else:
                        break
                timeoutmsg = "Failed to start the ICAT proposal"
                self._icat_wait_until_state(["STANDBY"], timeout=None)
        except gevent.Timeout:
            timeoutmsg = f"{timeoutmsg} ({self.icat_status})"
            if exception is None:
                raise RuntimeError(timeoutmsg)
            else:
                raise RuntimeError(timeoutmsg) from exception

    def _icat_set_sample(self, sample, timeout=3):
        """
        :param str sample:
        :param num timeout:
        :raises RuntimeError: timeout
        """
        exception = None
        try:
            with gevent.Timeout(timeout):
                timeoutmsg = "Failed to stop the running ICAT dataset"
                self._icat_ensure_notrunning(timeout=None)
                timeoutmsg = "Failed to set the ICAT sample name"
                while True:
                    try:
                        self.metadata_experiment.sample = sample
                        # Clears dataset name in ICAT servers
                    except Exception as e:
                        exception = e
                        if self.icat_state == "STANDBY":
                            gevent.sleep(0.1)
                        else:
                            raise
                    else:
                        break
                timeoutmsg = "Failed to start the ICAT sample"
                self._icat_wait_until_state(["STANDBY"], timeout=None)
        except gevent.Timeout:
            timeoutmsg = f"{timeoutmsg} ({self.icat_status})"
            if exception is None:
                raise RuntimeError(timeoutmsg)
            else:
                raise RuntimeError(timeoutmsg) from exception

    def _icat_set_dataset(self, dataset, timeout=3):
        """
        :param str dataset:
        :param num timeout:
        :raises RuntimeError: timeout
        """
        exception = None
        try:
            with gevent.Timeout(timeout):
                timeoutmsg = "Failed to stop the running ICAT dataset"
                self._icat_ensure_notrunning(timeout=None)
                timeoutmsg = "Failed to set the ICAT dataset name"
                while True:
                    try:
                        self.metadata_manager.datasetName = dataset
                    except Exception as e:
                        exception = e
                        if self.icat_state == "STANDBY":
                            gevent.sleep(0.1)
                        else:
                            raise
                    else:
                        break
                timeoutmsg = "Failed to start the ICAT dataset"
                self._icat_wait_until_state(["ON"], timeout=None)
        except gevent.Timeout:
            timeoutmsg = f"{timeoutmsg} ({self.icat_status})"
            if exception is None:
                raise RuntimeError(timeoutmsg)
            else:
                raise RuntimeError(timeoutmsg) from exception

    def newproposal(self, proposal_name):
        # beware: self.proposal getter and setter do different actions
        self.proposal = "" if not proposal_name else proposal_name
        self.sample = ""
        self.dataset = ""
        lprint(f"Proposal set to '{self.proposal}'\nData path: {self.get_path()}")

    def newsample(self, sample_name):
        # beware: self.sample getter and setter do different actions
        self.sample = "" if not sample_name else sample_name
        self.dataset = ""
        lprint(f"Sample set to '{self.sample}`\nData path: {self.root_path}")

    def newdataset(self, dataset_name):
        # beware: self.dataset getter and setter do different actions
        self.dataset = "" if not dataset_name else dataset_name
        lprint(f"Dataset set to '{self.dataset}`\nData path: {self.root_path}")
