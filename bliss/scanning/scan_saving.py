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
import datetime
import enum

from bliss import current_session
from bliss.config.settings import ParametersWardrobe
from bliss.config.conductor.client import get_redis_proxy
from bliss.data.node import datanode_factory
from bliss.scanning.writer.null import Writer as NullWriter
from bliss.scanning import writer as writer_module
from bliss.common.proxy import Proxy
from bliss.common import logtools
from bliss.icat.client import IcatTangoProxy
from bliss.icat.client import icat_client_from_config
from bliss.config.static import get_config
from bliss.config.settings import scan as scan_redis
from bliss.common.utils import autocomplete_property
from bliss.icat.proposal import Proposal
from bliss.icat.dataset_collection import DatasetCollection
from bliss.icat.dataset import Dataset


_SCAN_SAVING_CLASS = None

ScanSaving = Proxy(lambda: _SCAN_SAVING_CLASS or BasicScanSaving)


def set_scan_saving_class(klass):
    global _SCAN_SAVING_CLASS
    _SCAN_SAVING_CLASS = klass


class ESRFDataPolicyEvent(enum.Enum):
    Enable = "enabled"
    Disable = "disabled"
    Change = "changed"


logger = logging.getLogger(__name__)


class MissingParameter(ValueError):
    pass


class CircularReference(ValueError):
    pass


def with_eval_dict(method):
    """This passes a dictionary as named argument `eval_dict` to the method
    when it is not passed by the caller. This dictionary is used for caching
    parameter evaluations (user attributes and properties) in `EvalParametersWardrobe`.

    :param callable method: unbound method of `EvalParametersWardrobe`
    :returns callable:
    """

    @wraps(method)
    def eval_func(self, *args, **kwargs):
        # Create a cache dictionary if not provided by caller
        if "eval_dict" in kwargs:
            eval_dict = kwargs.get("eval_dict")
        else:
            eval_dict = None
        if eval_dict is None:
            logger.debug("create eval_dict (method {})".format(repr(method.__name__)))
            # Survives only for the duration of the call
            eval_dict = kwargs["eval_dict"] = {}
        if not eval_dict:
            self._update_eval_dict(eval_dict)
            logger.debug("filled eval_dict (method {})".format(repr(method.__name__)))
        # Evaluate method (passes eval_dict)
        return method(self, *args, **kwargs)

    return eval_func


class property_with_eval_dict(autocomplete_property):
    """Combine the `with_eval_dict` and `property` decorators
    """

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        if fget is not None:
            name = "_eval_getter_" + fget.__name__
            fget = with_eval_dict(fget)
            fget.__name__ = name
        if fset is not None:
            name = "_eval_setter_" + fset.__name__
            fset = with_eval_dict(fset)
            fset.__name__ = name
        super().__init__(fget=fget, fset=fset, fdel=fdel, doc=doc)


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

    NO_EVAL_PROPERTIES = set()

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
                if hasattr(self, field):
                    self.get_cached_property(field, eval_dict)
                if field not in eval_dict:
                    raise MissingParameter(
                        f"Parameter {repr(field)} is missing in {repr(template)}"
                    ) from None

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

    def _update_eval_dict(self, eval_dict):
        """Update the evaluation dictionary with user attributes (from Redis)
        and properties when missing.

        :param dict eval_dict:
        :returns dict:
        """
        fromredis = self.to_dict(export_properties=False)
        for k, v in fromredis.items():
            if k not in eval_dict:
                eval_dict[k] = v
        for prop in self._iter_eval_properties():
            if prop in eval_dict:
                continue
            self.get_cached_property(prop, eval_dict)

    def _iter_eval_properties(self):
        """Yield all properties that will be cached when updating the
        evaluation dictionary
        """
        for prop in self._property_attributes:
            if prop not in self.NO_EVAL_PROPERTIES:
                yield prop

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
        if isinstance(_prop, property_with_eval_dict):
            logger.debug("fget eval property " + repr(name))
            if is_circular_call(_prop.fget.__name__):
                raise CircularReference(
                    "Property {} contains a circular reference".format(repr(name))
                )
            r = _prop.fget(self, eval_dict=eval_dict)
        elif isinstance(_prop, property):
            logger.debug("fget normal property " + repr(name))
            r = _prop.fget(self)
        else:
            # Not a property
            r = getattr(self, name)
        eval_dict[name] = r
        logger.debug(f"     eval_dict[{repr(name)}] = {repr(r)}")
        return r

    def set_cached_property(self, name, value, eval_dict):
        """Pass `eval_dict` to a property setter.

        :param str name: property name
        :param any value:
        :param dict eval_dict:
        """
        _prop = getattr(self.__class__, name)
        if isinstance(_prop, property_with_eval_dict):
            logger.debug("fset eval property " + repr(name))
            if is_circular_call(_prop.fset.__name__):
                raise CircularReference(
                    "Property {} contains a circular reference".format(repr(name))
                )
            _prop.fset(self, value, eval_dict=eval_dict)
        elif isinstance(_prop, property):
            logger.debug("fset normal property " + repr(name))
            _prop.fset(self, value)
        else:
            # Not a property
            setattr(self, name, value)
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
        "user_name",
        "scan_name",
        "scan_number",
        "img_acq_device",
        "writer",
        "data_policy",
    ]
    REDIS_SETTING_PREFIX = "scan_saving"
    SLOTS = []

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
        if not name:
            name = str(uuid.uuid4().hex)
        super().__init__(
            f"{self.REDIS_SETTING_PREFIX}:{name}",
            default_values=self.DEFAULT_VALUES,
            property_attributes=self.PROPERTY_ATTRIBUTES,
            not_removable=self.DEFAULT_VALUES.keys(),
            connection=get_redis_proxy(caching=True),
        )

    def __dir__(self):
        keys = list(self.PROPERTY_ATTRIBUTES)
        keys.extend([p for p in self.DEFAULT_VALUES if not p.startswith("_")])
        keys.extend(
            [
                "clone",
                "get",
                "get_data_info",
                "get_path",
                "get_parent_node",
                "filename",
                "root_path",
                "data_path",
                "data_fullpath",
                "images_path",
                "writer_object",
                "file_extension",
                "scan_parent_db_name",
                "newproposal",
                "newcollection",
                "newsample",
                "newdataset",
                "on_scan_run",
            ]
        )
        return keys

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
    def name(self):
        """This is the init name or a uuid"""
        return self._wardr_name.split(self.REDIS_SETTING_PREFIX + ":")[-1]

    @property
    def session(self):
        """This give the name of the current session or 'default' if no current session is defined """
        try:
            return current_session.name
        except AttributeError:
            return "default"

    @property
    def date(self):
        return time.strftime(self.date_format)

    @property
    def user_name(self):
        return getpass.getuser()

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
        return self._get_root_path(base_path, eval_dict=eval_dict)

    @property_with_eval_dict
    def data_path(self, eval_dict=None):
        """Full path for the scan *data file* without the extension
        This is before the writer modifies the name (given by `self.filename`)
        """
        root_path = self.get_cached_property("root_path", eval_dict)
        return self._get_data_path(root_path, eval_dict=eval_dict)

    @property_with_eval_dict
    def data_fullpath(self, eval_dict=None):
        """Full path for the scan *data file* with the extension.
        This is before the writer modifies the name (given by `self.filename`)
        """
        data_path = self.get_cached_property("data_path", eval_dict)
        return self._get_data_fullpath(data_path, eval_dict=eval_dict)

    @with_eval_dict
    def _get_root_path(self, base_path, eval_dict=None):
        """Directory of the scan *data file*
        """
        template = os.path.join(base_path, self.template)
        return os.path.abspath(self.eval_template(template, eval_dict=eval_dict))

    @with_eval_dict
    def _get_data_path(self, root_path, eval_dict=None):
        """Full path for the scan *data file* without the extension
        This is before the writer modifies the name (given by `self.filename`)
        """
        data_filename = self.get_cached_property("eval_data_filename", eval_dict)
        return os.path.join(root_path, data_filename)

    @with_eval_dict
    def _get_data_fullpath(self, data_path, eval_dict=None):
        """Full path for the scan *data file* with the extension.
        This is before the writer modifies the name (given by `self.filename`)
        """
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
        types = ["container"] * len(parts)
        return list(zip(parts, types))

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

    def get_parent_node(self, create=True):
        """This method returns the parent node which should be used to publish new data

        :param bool create:
        :returns DatasetNode or None: can only return `None` when `create=False`
        """
        return self._get_node(self._db_path_items, create=create)

    def _get_node(self, db_path_items, create=True):
        """This method returns the parent node which should be used to publish new data

        :param list((str,str)) db_path_items:
        :param bool create:
        :returns DatasetNode or None: can only return `None` when `create=False`
        """
        node = None
        if create:
            for item_name, node_type in db_path_items:
                node = datanode_factory(
                    item_name, node_type=node_type, parent=node, create_not_state=True
                )
                self._fill_node_info(node, node_type)
        else:
            for item_name, node_type in db_path_items:
                node = datanode_factory(
                    item_name, node_type=node_type, parent=node, create_not_state=False
                )
                if node is None:
                    return None
        return node

    def _fill_node_info(self, node, node_type):
        """Add missing keys to node info
        """
        pass

    def _get_writer_class(self, writer_module_name):
        module_name = f"{writer_module.__name__}.{writer_module_name}"
        module = importlib.import_module(module_name)
        return getattr(module, "Writer")

    def newproposal(self, proposal_name):
        raise NotImplementedError("No data policy enabled")

    def newcollection(self, collection_name, **kw):
        raise NotImplementedError("No data policy enabled")

    def newsample(self, collection_name, **kw):
        raise NotImplementedError("No data policy enabled")

    def newdataset(self, dataset_name, **kw):
        raise NotImplementedError("No data policy enabled")

    def clone(self):
        new_scan_saving = self.__class__(self.name)
        for s in self.SLOTS:
            setattr(new_scan_saving, s, getattr(self, s))
        return new_scan_saving

    @property
    def elogbook(self):
        return None

    def on_scan_run(self, save):
        """Called at the start of a scan (in Scan.run)
        """
        pass


class ESRFScanSaving(BasicScanSaving):
    """Parameterized representation of the scan data file path
    according to the ESRF data policy

        base_path/template/data_filename+file_extension

    where the base_path is determined by the proposal name,
    the template is fixed to "{proposal_name}/{beamline}/{collection_name}/{collection_name}_{dataset_name}"
    and the data_filename is fixed to "{collection_name}_{dataset_name}".
    """

    DEFAULT_VALUES = {
        # default and not removable values
        "images_path_template": "scan{scan_number}",
        "images_prefix": "{img_acq_device}_",
        "date_format": "%Y%m%d",
        "scan_number_format": "%04d",
        "dataset_number_format": "%04d",
        # saved properties in Redis:
        "_writer_module": "nexus",
        "_proposal": "",
        "_ESRFScanSaving__proposal_timestamp": 0,
        "_collection": "",
        "_dataset": "",
        "_mount": "",
        "_reserved_dataset": "",
    }
    # Order important for resolving dependencies
    PROPERTY_ATTRIBUTES = BasicScanSaving.PROPERTY_ATTRIBUTES + [
        "template",
        "beamline",
        "proposal_name",
        "base_path",
        "collection_name",
        "dataset_name",
        "data_filename",
        "images_path_relative",
        "mount_point",
        "proposal",
        "collection",
        "dataset",
    ]
    SLOTS = BasicScanSaving.SLOTS + [
        "_icat_client",
        "_proposal_object",
        "_collection_object",
        "_dataset_object",
    ]
    REDIS_SETTING_PREFIX = "esrf_scan_saving"
    NO_EVAL_PROPERTIES = BasicScanSaving.NO_EVAL_PROPERTIES | {
        "proposal",
        "collection",
        "dataset",
    }

    def __init__(self, name):
        super().__init__(name)
        self._icat_client = None
        self._proposal_object = None
        self._collection_object = None
        self._dataset_object = None
        self._remove_deprecated()

    def _remove_deprecated(self):
        """Remove deprecated items from existing Redis databases"""
        stored = self.to_dict()
        if "_sample" in stored:
            # Deprecated in Bliss > 1.7.0
            value = stored["_sample"]
            self.remove("._sample")
            self._collection = value
        if "technique" in stored:
            # Deprecated in Bliss > 1.8.0
            self.remove("technique")

    def __dir__(self):
        keys = super().__dir__()
        keys.extend(
            ["proposal_type", "icat_root_path", "icat_data_path", "icat_data_fullpath"]
        )
        return keys

    @property
    def _session_config(self):
        """Current session config or static session config if no current session"""
        try:
            session_name = current_session.name
            config = current_session.config
        except AttributeError:
            # This may not be a session (and that's ok)
            session_name = self.name
            config = get_config()
        session_config = config.get_config(session_name)
        if session_config is None:
            return {}
        else:
            return session_config

    @property
    def _config_root(self):
        """Static config root"""
        try:
            return current_session.config.root
        except AttributeError:
            return get_config().root

    @property
    def scan_saving_config(self):
        return self._session_config.get(
            "scan_saving", self._config_root.get("scan_saving", {})
        )

    @property
    def data_policy(self):
        return "ESRF"

    @property
    def icat_client(self):
        if self._icat_client is None:
            try:
                self._icat_client = icat_client_from_config()
            except Exception:
                logtools.user_warning(
                    "The `icat_servers` beacon configuration is missing. Falling back to the deprecated ICAT tango servers."
                )
                self._icat_client = IcatTangoProxy(self.beamline, self.session)
        return self._icat_client

    @property
    def icat_proxy(self):
        # Note: obsolete. Exists for Flint only.
        if isinstance(self.icat_client, IcatTangoProxy):
            return self.icat_client
        return None

    @property
    def images_path_relative(self):
        # Always relative due to the data policy
        return True

        # todo remove images_path_relative completely from here!

    @property
    def beamline(self):
        bl = self.scan_saving_config.get("beamline")
        if not bl:
            return "{beamline}"
        # Alphanumeric, space, dash and underscore
        if not re.match(r"^[0-9a-zA-Z_\s\-]+$", bl):
            raise ValueError("Beamline name is invalid")
        return re.sub(r"[^0-9a-z]", "", bl.lower())

    @autocomplete_property
    def proposal(self):
        """Nothing is created in Redis for the moment.
        """
        if self._proposal_object is None:
            # This is just for caching purposes
            self._ensure_proposal()
            self._proposal_object = self._get_proposal_object(create=True)
        return self._proposal_object

    @autocomplete_property
    def collection(self):
        """Nothing is created in Redis for the moment.
        """
        if self._collection_object is None:
            # This is just for caching purposes
            self._ensure_collection()
            self._collection_object = self._get_collection_object(create=True)
        return self._collection_object

    @autocomplete_property
    def sample(self):
        return self.collection

    @property_with_eval_dict
    def sample_name(self, eval_dict=None):
        # Property of ESRFScanSaving so that it can be used in a template
        return self.get_cached_property("dataset", eval_dict).sample_name

    @property_with_eval_dict
    def dataset(self, eval_dict=None):
        """The dataset will be created in Redis when it does not exist yet.
        """
        if self._dataset_object is None:
            # This is just for caching purposes
            self._ensure_dataset()
            self._dataset_object = self._get_dataset_object(
                create=True, eval_dict=eval_dict
            )
        return self._dataset_object

    @property
    def template(self):
        return "{proposal_name}/{beamline}/{collection_name}/{collection_name}_{dataset_name}"

    @property
    def _icat_proposal_path(self):
        # See template
        return os.sep.join(self.icat_root_path.split(os.sep)[:-3])

    @property
    def _icat_collection_path(self):
        # See template
        return os.sep.join(self.icat_root_path.split(os.sep)[:-1])

    @property
    def _icat_dataset_path(self):
        # See template
        return self.icat_root_path

    @property_with_eval_dict
    def _db_path_keys(self, eval_dict=None):
        session = self.session
        base_path = self.get_cached_property("base_path", eval_dict).split(os.sep)
        base_path = [p for p in base_path if p]
        proposal = self.get_cached_property("proposal_name", eval_dict)
        collection = self.get_cached_property("collection_name", eval_dict)
        # When dataset="0001" the DataNode.name will be the integer 1
        # so use the file name instead.
        # dataset = self.get_cached_property("dataset", eval_dict)
        data_filename = self.get_cached_property("eval_data_filename", eval_dict)
        return [session] + base_path + [proposal, collection, data_filename]

    @property_with_eval_dict
    def _db_path_items(self, eval_dict=None):
        """For scan's parent node creation (see `get_parent_node`)

        :returns list(tuple):
        """
        parts = self.get_cached_property("_db_path_keys", eval_dict)
        types = ["container"] * len(parts)
        # See template:
        types[-3] = "proposal"
        types[-2] = "dataset_collection"
        types[-1] = "dataset"
        return list(zip(parts, types))

    @property_with_eval_dict
    def _db_proposal_items(self, eval_dict=None):
        return self.get_cached_property("_db_path_items", eval_dict)[:-2]

    @property_with_eval_dict
    def _db_collection_items(self, eval_dict=None):
        return self.get_cached_property("_db_path_items", eval_dict)[:-1]

    @property_with_eval_dict
    def _db_dataset_items(self, eval_dict=None):
        return self.get_cached_property("_db_path_items", eval_dict)

    def _fill_node_info(self, node, node_type):
        """Add missing keys to node info
        """
        if node_type == "proposal":
            info = {
                "__name__": self.proposal_name,
                "__path__": self._icat_proposal_path,
            }
        elif node_type == "dataset_collection":
            info = {
                "__name__": self.collection_name,
                "__path__": self._icat_collection_path,
                "Sample_name": self.collection_name,
            }
        elif node_type == "dataset":
            info = {
                "__name__": self.dataset_name,
                "__path__": self._icat_dataset_path,
                "__closed__": False,
            }
        else:
            return
        existing = list(node.info.keys())
        info = {k: v for k, v in info.items() if k not in existing}
        if info:
            node.info.update(info)

    @with_eval_dict
    def _get_proposal_node(self, create=True, eval_dict=None):
        """This method returns the proposal node

        :param bool create:
        :returns ProposalNode or None: can only return `None` when `create=False`
        """
        db_path_items = self.get_cached_property("_db_proposal_items", eval_dict)
        return self._get_node(db_path_items, create=create)

    @with_eval_dict
    def _get_collection_node(self, create=True, eval_dict=None):
        """This method returns the collection node

        :param bool create:
        :returns DatasetCollectionNode or None: can only return `None` when `create=False`
        """
        db_path_items = self.get_cached_property("_db_collection_items", eval_dict)
        return self._get_node(db_path_items, create=create)

    @with_eval_dict
    def _get_dataset_node(self, create=True, eval_dict=None):
        """This method returns the dataset node

        :param bool create:
        :returns DatasetNode or None: can only return `None` when `create=False`
        """
        db_path_items = self.get_cached_property("_db_dataset_items", eval_dict)
        return self._get_node(db_path_items, create=create)

    @property_with_eval_dict
    def base_path(self, eval_dict=None):
        """Root directory depending in the proposal type (inhouse, visitor, tmp)
        """
        return self._get_base_path(icat=False, eval_dict=eval_dict)

    @property_with_eval_dict
    def icat_base_path(self, eval_dict=None):
        """ICAT root directory depending in the proposal type (inhouse, visitor, tmp)
        """
        return self._get_base_path(icat=True, eval_dict=eval_dict)

    @property
    def date(self):
        if self._ESRFScanSaving__proposal_timestamp:
            tm = datetime.datetime.fromtimestamp(
                self._ESRFScanSaving__proposal_timestamp
            )
        else:
            tm = datetime.datetime.now()
        return tm.strftime(self.date_format)

    def _freeze_date(self):
        self._ESRFScanSaving__proposal_timestamp = time.time()

    def _unfreeze_date(self):
        self._ESRFScanSaving__proposal_timestamp = 0

    @with_eval_dict
    def _get_base_path(self, icat=False, eval_dict=None):
        """Root directory depending in the proposal type (inhouse, visitor, tmp)
        """
        ptype = self.get_cached_property("proposal_type", eval_dict)
        # When <type>_data_root is missing: use hardcoded default
        # When icat_<type>_data_root is missing: use <type>_data_root
        if ptype == "inhouse":
            template = self._get_mount_point(
                "inhouse_data_root", "/data/{beamline}/inhouse"
            )
            if icat:
                template = self._get_mount_point("icat_inhouse_data_root", template)
        elif ptype == "visitor":
            template = self._get_mount_point("visitor_data_root", "/data/visitor")
            if icat:
                template = self._get_mount_point("icat_visitor_data_root", template)
        else:
            template = self._get_mount_point("tmp_data_root", "/data/{beamline}/tmp")
            if icat:
                template = self._get_mount_point("icat_tmp_data_root", template)
        return self.eval_template(template, eval_dict=eval_dict)

    def _get_mount_point(self, key, default):
        """Get proposal type's mount point which defines `base_path`

        :param str key: scan saving configuration dict key
        :param str default: when key is not in configuration
        :returns str:
        """
        mount_points = self._mount_points_from_config(key, default)
        current_mp = mount_points.get(self.mount_point, None)
        if current_mp is None:
            # Take the first mount point when the current one
            # is not defined for this proposal type
            return mount_points[next(iter(mount_points.keys()))]
        else:
            return current_mp

    def _mount_points_from_config(self, key, default):
        """Get all mount points for the proposal type.

        :param str key: scan saving configuration dict key
        :param str default: when key is not in configuration
                            it returns {"": default})
        :returns dict: always at least one key-value pair
        """
        mount_points = self.scan_saving_config.get(key, default)
        if isinstance(mount_points, str):
            return {"": mount_points}
        else:
            return mount_points.to_dict()

    @property
    def mount_points(self):
        """All mount points of all proposal types

        :returns set(str):
        """
        mount_points = set()
        for k in ["inhouse_data_root", "visitor_data_root", "tmp_data_root"]:
            mount_points |= self._mount_points_from_config(k, "").keys()
            mount_points |= self._mount_points_from_config(f"icat_{k}", "").keys()
        return mount_points

    @property
    def mount_point(self):
        """Current mount point (defines `base_path` selection
        from scan saving configuration) for all proposal types
        """
        if self._mount is None:
            self._mount = ""
        return self._mount

    @mount_point.setter
    def mount_point(self, value):
        """
        :param str value:
        :raises ValueError: not in the available mount points
        """
        choices = self.mount_points
        if value not in choices:
            raise ValueError(f"The only valid mount points are {choices}")
        self._mount = value

    @property_with_eval_dict
    def icat_root_path(self, eval_dict=None):
        """Directory of the scan *data file* reachable by ICAT
        """
        base_path = self.get_cached_property("icat_base_path", eval_dict)
        return self._get_root_path(base_path, eval_dict=eval_dict)

    @property_with_eval_dict
    def icat_data_path(self, eval_dict=None):
        """Full path for the scan *data file* without the extension,
        reachable by ICAT
        """
        root_path = self.get_cached_property("icat_root_path", eval_dict)
        return self._get_data_path(root_path, eval_dict=eval_dict)

    @property_with_eval_dict
    def icat_data_fullpath(self, eval_dict=None):
        """Full path for the scan *data file* with the extension,
        reachable by ICAT
        """
        data_path = self.get_cached_property("icat_data_path", eval_dict)
        return self._get_data_fullpath(data_path, eval_dict=eval_dict)

    @property
    def data_filename(self):
        """File name template without extension
        """
        return "{collection_name}_{dataset_name}"

    def _reset_proposal(self):
        """(Re)-enter the default proposal
        """
        # Make sure the proposal name will be different:
        self._proposal = ""
        # ICAT dataset will be stored (if it exists):
        self.proposal_name = None

    def _reset_collection(self):
        """(Re)-enter the default collection
        """
        # Make sure the collection name will be different:
        self._collection = ""
        # ICAT dataset will be stored (if it exists):
        self.collection_name = None

    def _reset_dataset(self):
        """Next default dataset (re-entering not allowed)
        """
        # Avoid storing the ICAT dataset:
        self._dataset = ""
        self.dataset_name = None

    def _ensure_proposal(self):
        """Make sure a proposal is selected
        """
        if not self._proposal:
            self.proposal_name = None

    def _ensure_collection(self):
        """Make sure a collection is selected
        """
        if not self._collection:
            self.collection_name = None

    def _ensure_dataset(self):
        """Make sure a dataset is selected
        """
        if not self._dataset:
            self.dataset_name = None

    @property_with_eval_dict
    def proposal_name(self, eval_dict=None):
        if not self._proposal:
            self.set_cached_property("proposal_name", None, eval_dict)
        return self.eval_template(self._proposal, eval_dict=eval_dict)

    @proposal_name.setter
    def proposal_name(self, name, eval_dict=None):
        if name:
            # Alphanumeric, space, dash and underscore
            if not re.match(r"^[0-9a-zA-Z_\s\-]+$", name):
                raise ValueError("Proposal name is invalid")
            name = name.lower()
            name = re.sub(r"[^0-9a-z]", "", name)
        else:
            yymm = time.strftime("%y%m")
            name = f"{{beamline}}{yymm}"
        if name != self._proposal:
            self._close_dataset(eval_dict=eval_dict)
            self._close_collection()
            self._close_proposal()
            self._proposal = name
            self._freeze_date()
            self._reset_collection()
            if not isinstance(self.icat_client, IcatTangoProxy):
                self.icat_client.start_investigation(
                    proposal=self.proposal_name, beamline=self.beamline
                )
        if isinstance(self.icat_client, IcatTangoProxy):
            # Refresh the Tango state
            # Started in ICAT when tango state changed
            if self.icat_client.proposal != self.proposal_name:
                self.icat_client.proposal = self.proposal_name

    @property_with_eval_dict
    def proposal_type(self, eval_dict=None):
        proposal = self.get_cached_property("proposal_name", eval_dict)
        bl = self.get_cached_property("beamline", eval_dict)
        for proposal_prefix in ("blc", "ih", bl):
            if proposal.startswith(proposal_prefix):
                return "inhouse"
        for proposal_prefix in ("tmp", "temp", "test"):
            if proposal.startswith(proposal_prefix):
                return "tmp"
        return "visitor"

    @property_with_eval_dict
    def collection_name(self, eval_dict=None):
        if not self._collection:
            self.set_cached_property("collection_name", None, eval_dict)
        return self._collection

    @collection_name.setter
    def collection_name(self, name, eval_dict=None):
        if name:
            # Alphanumeric, space, dash and underscore
            if not re.match(r"^[0-9a-zA-Z_\s\-]+$", name):
                raise ValueError("Collection name is invalid")
            name = re.sub(r"[_\s\-]+", "_", name.strip())
        else:
            name = "sample"
        if name != self._collection:
            self._close_dataset(eval_dict=eval_dict)
            self._close_collection()
            self._ensure_proposal()
            self._collection = name
            self._reset_dataset()

    @property_with_eval_dict
    def dataset_name(self, eval_dict=None):
        if not self._dataset:
            self.set_cached_property("dataset_name", None, eval_dict)
        return self._dataset

    @dataset_name.setter
    def dataset_name(self, value, eval_dict=None):
        """
        :param int or str value:
        """
        self._close_dataset(eval_dict=eval_dict)
        self._ensure_proposal()
        self._ensure_collection()
        reserved = self._reserved_datasets()
        for dataset_name in self._dataset_name_generator(value):
            self._dataset = dataset_name
            root_path = self.root_path
            if not os.path.exists(root_path) and root_path not in reserved:
                self._reserved_dataset = root_path
                break

    def _reserved_datasets(self):
        """The dataset directories reserved by all sessions,
        whether the directories exist or not.
        """
        reserved = set()
        cnx = self._proxy._cnx()
        pattern = f"parameters:{self.REDIS_SETTING_PREFIX}:*:default"
        self_name = self.name
        for key in scan_redis(match=pattern, connection=cnx):
            name = key.split(":")[2]
            if name == self_name:
                continue
            scan_saving = self.__class__(name)
            reserved.add(scan_saving._reserved_dataset)
        return reserved

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

    def newproposal(self, proposal_name):
        """The proposal will be created in Redis if it does not exist already."""
        # beware: self.proposal getter and setter do different actions
        self.proposal_name = proposal_name
        msg = f"Proposal set to '{self.proposal}'\nData path: {self.get_path()}"
        logtools.elog_info(msg)
        logtools.user_print(msg)
        self._on_data_policy_changed(f"Proposal set to '{self.proposal}'")

    def newcollection(self, collection_name, sample_name=None, sample_description=None):
        """The dataset collection will be created in Redis if it does not exist already."""
        # beware: self.collection getter and setter do different actions
        self.collection_name = collection_name
        msg = f"Dataset collection set to '{self.collection}'\nData path: {self.root_path}"
        logtools.elog_info(msg)
        logtools.user_print(msg)
        self._on_data_policy_changed(f"Dataset collection set to '{self.collection}'")
        # fill metadata if provided
        if sample_name:
            self.collection.sample_name = sample_name
        if sample_description is not None:
            self.collection.sample_description = sample_description

    def newsample(self, collection_name, description=None):
        """Same as `newcollection` with sample name equal to the collection name.
        """
        self.newcollection(
            collection_name, sample_name=collection_name, sample_description=description
        )

    def newdataset(
        self, dataset_name, description=None, sample_name=None, sample_description=None
    ):
        """The dataset will be created in Redis if it does not exist already.
        Metadata will be gathered if not already done. RuntimeError is raised
        when the dataset is already closed.

        If `newdataset` is not used, the metadata gathering is done at the
        start of the first scan that aves data.
        """
        # beware: self.dataset_name getter and setter do different actions
        _dataset = self._dataset
        self.dataset_name = dataset_name
        try:
            self._init_dataset()
        except Exception:
            if _dataset is not None:
                self._dataset = _dataset
            raise

        msg = f"Dataset set to '{self.dataset}'\nData path: {self.root_path}"
        logtools.elog_info(msg)
        logtools.user_print(msg)
        self._on_data_policy_changed(f"Dataset set to '{self.dataset_name}'")

        if sample_name:
            self.dataset.sample_name = sample_name
        if sample_description is not None:
            self.dataset.sample_description = sample_description
        if description is not None:
            self.dataset.description = description

    def endproposal(self):
        """Close the active dataset (if any) and go to the default inhouse proposal
        """
        self._enddataset()
        self._reset_proposal()
        self._on_data_policy_changed(f"Proposal set to '{self.proposal_name}'")

    def enddataset(self):
        """Close the active dataset (if any) and go the the next dataset
        """
        self._enddataset()
        self._on_data_policy_changed(f"Dataset set to '{self.dataset_name}'")

    def _enddataset(self):
        self.dataset_name = None

    def _on_data_policy_changed(self, event):
        current_session._emit_event(
            ESRFDataPolicyEvent.Change, message=event, data_path=self.root_path
        )

    def _get_proposal_object(self, create=True):
        """Create a new Proposal instance.

        :param bool create: Create in Redis when it does not exist
        """
        if not self._proposal:
            raise RuntimeError("proposal not specified")
        node = self._get_proposal_node(create=create)
        if node is None:
            raise RuntimeError("proposal does not exist in Redis")
        return Proposal(node)

    def _get_collection_object(self, create=True):
        """Create a new DatasetCollection instance.

        :param bool create: Create in Redis when it does not exist
        """
        if not self._proposal:
            raise RuntimeError("proposal not specified")
        if not self._collection:
            raise RuntimeError("collection not specified")
        node = self._get_collection_node(create=create)
        if node is None:
            raise RuntimeError("collection does not exist in Redis")
        return DatasetCollection(node)

    @with_eval_dict
    def _get_dataset_object(self, create=True, eval_dict=None):
        """Create a new Dataset instance. The Dataset may be already closed,
        this is not checked in this method.

        :param bool create: Create in Redis when it does not exist
        :raises RuntimeError: this happens when
                            - the dataset is not fully defined yet
                            - the dataset does not exist in Redis and create=False
        """
        if not self._proposal:
            raise RuntimeError("proposal not specified")
        if not self._collection:
            raise RuntimeError("collection not specified")
        if not self._dataset:
            raise RuntimeError("dataset not specified")
        node = self._get_dataset_node(create=create, eval_dict=eval_dict)
        if node is None:
            raise RuntimeError("dataset does not exist in Redis")
        return Dataset(node)

    @property
    def elogbook(self):
        return self.icat_client

    def _close_proposal(self):
        """Close the current proposal.
        """
        self._proposal_object = None
        self._proposal = ""

    def _close_collection(self):
        """Close the current collection.
        """
        self._collection_object = None
        self._collection = ""

    @with_eval_dict
    def _close_dataset(self, eval_dict=None):
        """Close the current dataset. This will NOT create the dataset in Redis
        if it does not exist yet. If the dataset if already closed it does NOT
        raise an exception.
        """
        dataset = self._dataset_object
        if dataset is None:
            # The dataset object has not been cached
            try:
                dataset = self._get_dataset_object(create=False, eval_dict=eval_dict)
            except RuntimeError:
                # The dataset is not fully defined or does not exist.
                # Do nothing in that case.
                dataset = None

        if dataset is not None:
            if not dataset.is_closed:
                try:
                    # Finalize in Redis and send to ICAT
                    dataset.close(self.icat_client)
                except Exception as e:
                    if (
                        not dataset.node.exists
                        or dataset.collection is None
                        or dataset.proposal is None
                        or not dataset.collection.node.exists
                        or not dataset.proposal.node.exists
                    ):
                        # Failure due to missing Redis nodes: recreate them and try again
                        self.get_parent_node(create=True)
                        dataset = self._get_dataset_object(
                            create=False, eval_dict=eval_dict
                        )
                        try:
                            dataset.close(self.icat_client)
                        except Exception as e2:
                            self._dataset_object = None
                            self._dataset = ""
                            raise RuntimeError("The dataset cannot be closed.") from e2
                        else:
                            self._dataset_object = None
                            self._dataset = ""
                            logtools.elog_warning(
                                f"The ICAT metadata of {self._dataset} is incomplete."
                            )
                            raise RuntimeError(
                                "The dataset was closed but its ICAT metadata is incomplete."
                            ) from e

        self._dataset_object = None
        self._dataset = ""

    def on_scan_run(self, save):
        """Called at the start of a scan (in Scan.run)
        """
        if save:
            self._init_dataset()

    def _init_dataset(self):
        """The dataset will be created in Redis if it does not exist already.
        Metadata will be gathered if not already done. RuntimeError is raised
        when the dataset is already closed.
        """
        dataset = self.dataset  # Created in Redis when missing
        if dataset.is_closed:
            raise RuntimeError("Dataset is already closed (choose a different name)")
        dataset.gather_metadata(on_exists="skip")
