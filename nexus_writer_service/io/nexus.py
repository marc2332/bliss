# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2020 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Nexus API
"""

import h5py
import datetime
import numpy
import os
import errno
import re
import pprint
import logging
import bliss
import gevent
import warnings
from functools import wraps
from io import StringIO
from collections import Counter
from contextlib import contextmanager
from silx.io.dictdump import dicttojson, dicttoini
from .io_utils import mkdir
from ..utils import data_merging
from ..utils.process_utils import file_processes
from ..utils.async_utils import SharedLockPool
from ..utils.exceptions import iter_chained_exception
from silx.io import h5py_utils

DEFAULT_PLOT_NAME = "plotselect"

try:
    h5py.VirtualLayout
except AttributeError:
    HASVIRTUAL = False
else:
    HASVIRTUAL = True

logger = logging.getLogger(__name__)

nxcharUnicode = h5py.special_dtype(vlen=str)
nxcharBytes = h5py.special_dtype(vlen=bytes)


class NexusInstanceExists(Exception):
    pass


def asNxChar(s, raiseExtended=True):
    """
    Convert to Variable-length string (array or scalar).
    Uses UTF-8 encoding when possible, otherwise byte-strings
    are used (unless raiseExtended is set).

    :param s: string or sequence of strings
              string types: unicode, bytes, fixed-length numpy
    :param bool raiseExtended: raise UnicodeDecodeError for bytes
                               with extended ASCII encoding
    :returns np.ndarray(nxcharUnicode or nxcharBytes):
    :raises UnicodeDecodeError: extended ASCII encoding
    """
    if isinstance(s, numpy.ndarray) and s.dtype in (nxcharBytes, nxcharUnicode):
        return s
    try:
        # dtype=nxcharUnicode will not attempt decoding bytes
        # so readers will get UnicodeDecodeError when bytes
        # are extended ASCII encoded. So do this instead:
        numpy.array(s, dtype=str)
    except UnicodeDecodeError:
        # Reason: byte-string with extended ASCII encoding (e.g. Latin-1)
        # Solution: save as byte-string or raise exception
        # Remark: Clients will read back the data exactly as it is written.
        #         However the HDF5 character set is h5py.h5t.CSET_ASCII
        #         which is strictly speaking not correct.
        if raiseExtended:
            raise
        return numpy.array(s, dtype=nxcharBytes)
    else:
        return numpy.array(s, dtype=nxcharUnicode)


def isNxChar(data):
    """String from the Nexus point of view
    """
    if isinstance(data, (str, bytes)):
        return True
    elif isinstance(data, numpy.ndarray):
        return numpy.issubdtype(data.dtype, numpy.bytes_) or numpy.issubdtype(
            data.dtype, numpy.str_
        )
    else:
        return False


def asNxType(data):
    """Convert data to Nexus data type
    """
    if isNxChar(data):
        return asNxChar(data)
    elif isinstance(data, (list, tuple)) and data:
        if all([isinstance(v, (str, bytes)) for v in data]):
            return asNxChar(data)
    return data


def createNxValidate(createkws):
    if "data" in createkws:
        createkws["data"] = asNxType(createkws["data"])
    dtype = createkws.get("dtype")
    if dtype is not None:
        if dtype is str:
            createkws["dtype"] = nxcharUnicode
            createkws.pop("fillvalue")
        elif dtype is bytes:
            createkws["dtype"] = nxcharBytes
            createkws.pop("fillvalue")


def ensure_timezone(tm):
    """Make sure the datetime has a timezone.
    Take the current system timezone when missing.

    :param datetime tm:
    :returns datetime:
    """
    if tm.tzinfo is None:
        return tm.astimezone()
    else:
        return tm


def datetime_to_nexus(tm):
    """
    Format datetime for Nexus saving

    :param datetime.datetime tm:
    :returns np.ndarray: variable length string
    """
    return asNxType(ensure_timezone(tm).isoformat())


def timestamp():
    """
    Timestamp for Nexus saving

    :returns np.ndarray: variable length string
    """
    return datetime_to_nexus(datetime.datetime.now())


def hdf5_sep(func):
    @wraps(func)
    def as_os_path(*args, sep="/"):
        args = [re.sub(r"[\/]+", os.sep, x) for x in args]
        ret = func(*args)
        if isinstance(ret, str):
            ret = ret.replace(os.sep, sep)
        return ret

    return as_os_path


@hdf5_sep
def hdf5_normpath(path):
    return os.path.normpath(path)


@hdf5_sep
def hdf5_relpath(path, refpath):
    return os.path.relpath(path, refpath)


@hdf5_sep
def hdf5_split(path):
    return os.path.split(path)


@hdf5_sep
def hdf5_basename(path):
    return os.path.basename(path)


@hdf5_sep
def hdf5_dirname(path):
    return os.path.dirname(path)


@hdf5_sep
def hdf5_join(*args):
    return os.path.join(*args)


def splitUri(uri):
    """
    Split Uniform Resource Identifier (URI)

    :param str uri: URI
    :return tuple: filename(str), group(str)
    """
    try:
        i = uri.index("::")
    except (IndexError, ValueError):
        filename = uri
        h5groupname = "/"
    else:
        filename = uri[:i]
        h5groupname = uri[i + 2 :]
        if h5groupname[0] != "/":
            h5groupname = "/" + h5groupname
    return filename, h5groupname


def normUri(uri):
    """Normalize uri

    :param str uri: URI
    :return str:
    """
    filename, path = splitUri(uri)
    filename = os.path.normpath(filename)
    path = hdf5_normpath(path)
    return filename + "::" + path


def _dereference_node(parent, name):
    """
    :param h5py.Dataset or h5py.Group parent:
    :param str name: appended to uri
    :returns str: uri
    """
    try:
        lnk = parent.get(name, default=None, getlink=True)
    except (KeyError, RuntimeError):
        return hdf5_join(getUri(parent), name)
    else:
        if isinstance(lnk, h5py.SoftLink):
            path = lnk.path
            if not path.startswith("/"):
                parts = name.split("/")[:-1]
                path = hdf5_join(parent.name, *parts, path)
            return parent.file.filename + "::" + hdf5_normpath(path)
        elif isinstance(lnk, h5py.ExternalLink):
            efilename = lnk.filename
            if not os.path.isabs(efilename):
                dirname = os.path.dirname(parent.file.filename)
                efilename = os.path.normpath(os.path.join(dirname, efilename))
            return efilename + "::" + lnk.path
        else:
            return hdf5_join(getUri(parent), name)


def dereference(uri, name=None):
    """Get full URI of dataset or group.
    Follows links until destination is found.

    :param h5py.Dataset or h5py.Group or str uri:
    :param str name: appended to uri
    :returns str: uri
    """
    if not isinstance(uri, (str, bytes)):
        uri = getUri(uri)
    if name:
        uri = hdf5_join(uri, name)
    filename, path = splitUri(uri)
    uri2 = uri
    istart = 1
    try:
        with File(filename, mode="r") as f:
            while True:
                parts = path.split("/")[1:]
                for i in range(istart, len(parts) + 1):
                    path2 = hdf5_join(*parts[:i])
                    filename2, path2 = splitUri(_dereference_node(f, path2))
                    path2 = hdf5_join(path2, *parts[i:])
                    uri2 = filename2 + "::" + path2
                    if uri != uri2:
                        if filename == filename2:
                            path = path2
                            istart = i + 1
                            break
                        else:
                            return dereference(uri2)
                else:
                    break
    except OSError:
        pass
    return uri2


def getUri(node):
    """
    Get full URI of dataset or group

    :param h5py.Dataset or h5py.Group:
    :returns str:
    """
    return node.file.filename + "::" + node.name


def relUri(uri, refuri):
    """
    Get uri relative to another uri

    :param str or 2-tuple uri:
    :param str or 2-tuple refuri:
    :returns (str, str):
    """
    if isinstance(uri, tuple):
        a, b = uri
    else:
        a, b = splitUri(uri)
    if isinstance(refuri, tuple):
        refa, refb = refuri
    else:
        refa, refb = splitUri(refuri)
    if a == refa:
        reta = "."
        retb = hdf5_relpath(b, refb)
    else:
        abase = os.path.basename(a)
        adir = os.path.dirname(a)
        refadir = os.path.dirname(refa)
        if adir and refadir:
            adir = os.path.relpath(adir, refadir)
        reta = os.path.join(adir, abase)
        retb = b
    return reta, retb


@contextmanager
def uriContext(uri, **kwargs):
    """
    HDF5 group/dataset context

    :param str uri:
    :yields h5py.Group/h5py.Dataset:
    """
    filename, path = splitUri(uri)
    try:
        with File(filename, **kwargs) as f:
            try:
                item = f[path]
            except KeyError:
                item = None
            yield item
    except OSError:
        yield None


def exists(uri):
    """
    Check whether URI exists

    :param str uri:
    :returns bool:
    """
    try:
        with uriContext(uri, mode="r") as node:
            return node is not None
    except (OSError, KeyError) as e:
        logger.warning(str(e))
        pass
    return False


def uriContains(uri, datasets=None, attributes=None):
    """
    :param str uri:
    :returns bool:
    """
    if not datasets:
        datasets = []
    if not attributes:
        attributes = []
    try:
        with uriContext(uri, mode="r") as node:
            for dset in datasets:
                if dset not in node:
                    return False
            if attributes:
                attrs = node.attrs
                for attr in attributes:
                    if attr not in attrs:
                        return False
    except Exception:
        return False
    return True


def nxComplete(uri):
    """
    :param str uri:
    :returns bool:
    """
    return uriContains(uri, datasets=["end_time"])


def iterup(h5group, includeself=True):
    """
    Iterator which yields all parent h5py.Group's up till root

    :param h5py.Group h5group:
    :param bool includeself:
    :returns generator:
    """
    if includeself:
        yield h5group
    while h5group.parent != h5group:
        h5group = h5group.parent
        yield h5group


def isLink(parent, name):
    """
    Check whether node is h5py.SoftLink or h5py.ExternalLink

    :param h5py.Group parent:
    :param str name:
    :returns bool:
    """
    try:
        lnk = parent.get(name, default=None, getlink=True)
    except (KeyError, RuntimeError):
        return False
    else:
        return isinstance(lnk, (h5py.SoftLink, h5py.ExternalLink))


def h5Name(h5group):
    """
    HDF5 Dataset of Group name

    :param h5py.Group h5group:
    :returns str:
    """
    return h5group.name.split("/")[-1]


def as_str(s):
    """
    :param str or bytes s:
    :returns str:
    """
    try:
        return s.decode()
    except AttributeError:
        return s


def attr_as_str(node, attr, default):
    """
    Get attribute value (scalar or sequence) with type `str`.

    :param h5py.Group or h5py.Dataset node:
    :param str attr:
    :param default:
    :return str or sequence(str):
    """
    v = node.attrs.get(attr, default)
    if isinstance(v, str):
        return v
    elif isinstance(v, bytes):
        return v.decode()
    elif isinstance(v, tuple):
        return tuple(as_str(s) for s in v)
    elif isinstance(v, list):
        return list(as_str(s) for s in v)
    elif isinstance(v, numpy.ndarray):
        return numpy.array(list(as_str(s) for s in v))
    else:
        return v


def nxClass(h5group):
    """
    Nexus class of existing h5py.Group (None when no Nexus instance)

    :param h5py.Group h5group:
    :returns str or None:
    """
    return attr_as_str(h5group, "NX_class", None)


def isNxClass(h5group, *classes):
    """
    Nexus class of existing h5py.Group (None when no Nexus instance)

    :param h5py.Group h5group:
    :param *classes: list(str) of Nexus classes
    :returns bool:
    """
    return nxClass(h5group) in classes


def raiseIsNxClass(h5group, *classes):
    """
    :param h5py.Group h5group:
    :param *classes: list(str) of Nexus classes
    :raises RuntimeError:
    """
    if isNxClass(h5group, *classes):
        raise RuntimeError("Nexus class should not be one of these: {}".format(classes))


def raiseIsNotNxClass(h5group, *classes):
    """
    :param h5py.Group h5group:
    :param *classes: list(str) of Nexus classes
    :raises RuntimeError:
    """
    if not isNxClass(h5group, *classes):
        raise RuntimeError("Nexus class not in {}".format(classes))


def nxClassInstantiate(parent, name, nxclass, raise_on_exists=False):
    """
    Create `parent[name]` or check its nexus class.

    :param h5py.Group parent:
    :param str or None name: `None` means the 
    :param str nxclass: nxclass of the parent when `name is None`
    :param bool raise_on_exists:
    :returns bool: new instance created
    :raises RuntimeError: wrong Nexus class
    :raises NexusInstanceExists:
    """
    if name is None:
        exists = nxClass(parent) is not None
        group = parent
    else:
        try:
            group = parent.create_group(name, track_order=False)
            exists = False
        except Exception as e:
            exists = True
            group = parent[name]
            if raise_on_exists:
                logger.warning(e)
                raise NexusInstanceExists(group.name)
    if exists:
        raiseIsNotNxClass(group, nxclass)
    return not exists


def updated(h5group, final=False, parents=False):
    """
    h5py.Group has changed

    :param h5py.Group h5group:
    :param bool final: mark as final update
    :param bool parents: mark parents as well
    """
    tm = timestamp()
    for group in iterup(h5group):
        nxclass = nxClass(group)
        if nxclass is None:
            if parents:
                continue
            else:
                break
        elif nxclass in ["NXentry", "NXsubentry"]:
            if "start_time" not in group:
                group["start_time"] = tm
            if final:
                updateDataset(group, "end_time", tm)
        elif nxclass in ["NXprocess", "NXnote"]:
            updateDataset(group, "date", tm)
        # h5py issue #1641
        # elif nxclass == "NXroot":
        #    updateAttribute(group, "file_update_time", tm)
        if not parents:
            break


def updateDataset(parent, name, data):
    """
    :param h5py.Group parent:
    :param str name:
    :param data:
    """
    if name in parent:
        parent[name][()] = asNxType(data)
    else:
        parent[name] = asNxType(data)


def updateAttribute(parent, name, value):
    """
    :param h5py.Group parent:
    :param str name:
    :param value:
    """
    if value is None:
        return
    try:
        parent.attrs[name] = asNxType(value)
    except Exception as e:
        if "B-tree" in str(e):
            warnings.warn(
                f"Cannot set attribute {repr(name)}: h5py issue #1641", UserWarning
            )
        else:
            raise


def nxClassInit(
    parent, name, nxclass, parentclasses=None, raise_on_exists=False, **kwargs
):
    """
    Initialize Nexus class instance. When it does exist: create
    default attributes and datasets or raise exception.

    :param h5py.Group parent:
    :param str name:
    :param str nxclass:
    :param tuple parentclasses:
    :param bool raise_on_exists:
    :param **kwargs: see `nxInit`
    :returns h5py.Group:
    :raises RuntimeError: wrong Nexus class or parent
                          not an Nexus class instance
    :raises NexusInstanceExists:
    """
    if parentclasses:
        raiseIsNotNxClass(parent, *parentclasses)
    else:
        raiseIsNxClass(parent, None)
    if nxClassInstantiate(parent, name, nxclass, raise_on_exists=raise_on_exists):
        h5group = parent[name]
        nxAddAttrInit(kwargs, "NX_class", nxclass)
        nxInit(h5group, **kwargs)
        updated(h5group)
        return h5group
    else:
        return parent[name]


def nxRootInit(h5group, rootattrs=None):
    """
    Initialize NXroot instance

    :param h5py.Group h5group:
    :param dict rootattrs:
    :raises ValueError: not root
    :raises RuntimeError: wrong Nexus class
    """
    if h5group.name != "/":
        raise ValueError("Group should be the root")
    if rootattrs is None:
        rootattrs = {}
    if nxClassInstantiate(h5group, None, "NXroot"):
        updateAttribute(h5group, "file_time", timestamp())
        updateAttribute(h5group, "file_name", h5group.file.filename)
        updateAttribute(h5group, "HDF5_Version", h5py.version.hdf5_version)
        updateAttribute(h5group, "h5py_version", h5py.version.version)
        updateAttribute(h5group, "creator", "Bliss")
        updateAttribute(h5group, "creator_version", bliss.__version__)
        updateAttribute(h5group, "NX_class", "NXroot")
        for attr, value in rootattrs.items():
            updateAttribute(h5group, attr, value)
        updated(h5group)


def nxInit(h5group, attrs=None, datasets=None):
    """
    Initialize NXclass instance

    :param h5py.Group h5group:
    :param dict attrs:
    :param dict datasets:
    """
    if datasets:
        for k, v in datasets.items():
            updateDataset(h5group, k, v)
    if attrs:
        for k, v in attrs.items():
            updateAttribute(h5group, k, v)


def nxAddDatasetInit(dic, key, value):
    """
    Add key as dataset to NXclass instantiation

    :param dict dic:
    :param key:
    :param value:
    """
    dic["datasets"] = dic.get("datasets", {})
    dic["datasets"][key] = value


def nxAddAttrInit(dic, key, value):
    """
    Add key as attribute to NXclass instantiation

    :param dict dic:
    :param key:
    :param value:
    """
    dic["attrs"] = dic.get("attrs", {})
    dic["attrs"][key] = value


def nxEntryInit(
    parent, name, sub=False, start_time=None, raise_on_exists=False, **kwargs
):
    """
    Initialize NXentry and NXsubentry instance

    :param h5py.Group parent:
    :param bool sub:
    :param datetime start_time: 'now' when missing
    :param bool raise_on_exists:
    :param **kwargs: see `nxInit`
    :returns h5py.Group:
    :raises RuntimeError: wrong NX_class or parent NX_class
    :raises NexusInstanceExists:
    """
    if sub:
        nxclass = "NXsubentry"
        parents = ("NXentry",)
    else:
        nxclass = "NXentry"
        parents = ("NXroot",)
    raiseIsNotNxClass(parent, *parents)
    if nxClassInstantiate(parent, name, nxclass, raise_on_exists=raise_on_exists):
        h5group = parent[name]
        if start_time is None:
            start_time = timestamp()
        else:
            start_time = datetime_to_nexus(start_time)
        nxAddDatasetInit(kwargs, "start_time", start_time)
        nxAddAttrInit(kwargs, "NX_class", nxclass)
        nxInit(h5group, **kwargs)
        updated(h5group)
        return h5group
    else:
        return parent[name]


def nxProcessConfigurationInit(
    parent, date=None, configdict=None, type="json", indent=2, raise_on_exists=False
):
    """
    Initialize NXnote instance

    :param h5py.Group parent:
    :param datetime date:
    :param dict configdict:
    :param str type: 'json' or 'ini' or None (pprint)
    :param num indent: pretty-string with indent level
    :returns h5py.Group:
    :raises RuntimeError: parent not NXprocess
    :raises NexusInstanceExists:
    """
    raiseIsNotNxClass(parent, "NXprocess")
    if configdict is not None:
        data = ""
        with StringIO() as s:
            if type == "json":
                dicttojson(configdict, s, indent=indent)
                data = s.getvalue()
            elif type == "ini":
                dicttoini(configdict, s)
                data = s.getvalue()
        if not data:
            data = pprint.pformat(configdict, indent=indent)
            type = "txt"
    else:
        data = None
        type = None
    return nxNote(
        parent,
        "configuration",
        data=data,
        type=type,
        date=date,
        raise_on_exists=raise_on_exists,
    )


def nxProcess(parent, name, configdict=None, raise_on_exists=False, **kwargs):
    """
    Get NXprocess instance (create or raise when missing)

    :param h5py.Group parent:
    :param str name:
    :param dict configdict:
    :param **kwargs: see `nxProcessConfigurationInit`
    :returns h5py.Group:
    :raises RuntimeError: wrong Nexus class or parent not NXentry
    :raises NexusInstanceExists:
    """
    raiseIsNotNxClass(parent, "NXentry")
    if nxClassInstantiate(parent, name, "NXprocess", raise_on_exists=raise_on_exists):
        h5group = parent[name]
        updateDataset(h5group, "program", "bliss")
        updateDataset(h5group, "version", bliss.__version__)
        updateAttribute(h5group, "NX_class", "NXprocess")
        updated(h5group)
    else:
        h5group = parent[name]
    nxProcessConfigurationInit(
        h5group, configdict=configdict, raise_on_exists=raise_on_exists, **kwargs
    )
    nxClassInit(h5group, "results", "NXcollection")
    return h5group


def nxNote(parent, name, data=None, type=None, date=None, raise_on_exists=False):
    """
    Get NXnote instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param str data:
    :param str type:
    :param datetime date:
    :param bool raise_on_exists:
    :return h5py.Group:
    :raises RuntimeError: wrong Nexus class or parent
                          not an Nexus class instance
    :raises NexusInstanceExists:
    """
    raiseIsNxClass(parent, None)
    if nxClassInstantiate(parent, name, "NXnote", raise_on_exists=raise_on_exists):
        h5group = parent[name]
        updateAttribute(h5group, "NX_class", "NXnote")
        update = True
    else:
        h5group = parent[name]
        update = False
    if data is not None:
        updateDataset(h5group, "data", data)
        update = True
    if type is not None:
        updateDataset(h5group, "type", type)
        update = True
    if date:
        updateDataset(h5group, "date", datetime_to_nexus(date))
    elif update:
        updated(h5group)
    return h5group


def _isErrno(ex, errno):
    """
    :param BaseException ex:
    :param int errno:
    :returns bool:
    """
    return f"errno = {errno}" in str(ex)


def _isLockedError(ex):
    """
    :param BaseException ex:
    :returns bool:
    """
    return _isErrno(ex, errno.EAGAIN) and "unable to lock file" in str(ex)


def isLockedError(ex):
    """
    :param BaseException ex:
    :returns bool:
    """
    for exi in iter_chained_exception(ex):
        if _isLockedError(exi):
            return True
    return False


def lockedErrorMessage(filename):
    """
    :param str filename:
    :returns str:
    """
    pattern = ".+{}$".format(os.path.basename(filename))
    procs = file_processes(pattern)
    if procs:
        msg = f"The Nexus file is locked: {repr(filename)}"
        msg += "\nThese local processes are accessing the file but not necessarily locking it:"
        for _, proc in procs:
            msg += f"\n {proc}"
        msg += "\nRemote processes are not shown."
    else:
        msg = f"The Nexus file is locked by a remote process: {repr(filename)}"
    msg += "\nTerminate the locking process or use a different acquisition file in order to continue."
    # msg += " External applications should open the file in read-only mode with file locking disabled."
    return msg + "\n"


class File(h5py_utils.File):

    _LOCKPOOL = SharedLockPool()

    def __init__(self, filename, **kwargs):
        """
        :param str filename:
        :param **kwargs: see `h5py_utils.File.__init__`
        """
        with self._protect_init(filename):
            super().__init__(filename, **kwargs)

    @contextmanager
    def _protect_init(self, filename):
        """Makes sure no other file is opened/created
        or protected sections associated to the filename
        are executed.
        """
        lockname = os.path.abspath(filename)
        with self._LOCKPOOL.acquire(None):
            with self._LOCKPOOL.acquire(lockname):
                yield

    @contextmanager
    def protect(self):
        """Protected section associated to this file.
        """
        lockname = os.path.abspath(self.filename)
        with self._LOCKPOOL.acquire(lockname):
            yield


class nxRoot(File):
    def __init__(self, filename, mode="r", rootattrs=None, **kwargs):
        """
        :param str filename:
        :param str mode:
        :param dict rootattrs: extra attributes to the default ones
        :param **kwargs: see `h5py.File.__init__`
        """
        with self._protect_init(filename):
            if mode != "r":
                mkdir(os.path.dirname(filename))
            super().__init__(filename, mode=mode, **kwargs)
            nxRootInit(self, rootattrs)


def nxEntry(root, name, **kwargs):
    """
    Get NXentry instance (initialize when missing)

    :param h5py.Group root:
    :param str name:
    :param **kwargs: see `nxEntryInit`
    :returns h5py.Group:
    """
    return nxEntryInit(root, name, sub=False, **kwargs)


def nxSubEntry(parent, name, **kwargs):
    """
    Get NXsubentry instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxEntryInit`
    :returns h5py.Group:
    """
    return nxEntryInit(parent, name, sub=True, **kwargs)


def nxCollection(parent, name, **kwargs):
    """
    Get NXcollection instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    return nxClassInit(parent, name, "NXcollection", **kwargs)


def nxInstrument(parent, name="instrument", **kwargs):
    """
    Get NXinstrument instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    return nxClassInit(
        parent, name, "NXinstrument", parentclasses=("NXentry",), **kwargs
    )


def nxDetector(parent, name, **kwargs):
    """
    Get NXdetector instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    return nxClassInit(
        parent, name, "NXdetector", parentclasses=("NXinstrument",), **kwargs
    )


def nxPositioner(parent, name, **kwargs):
    """
    Get NXpositioner instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    return nxClassInit(
        parent, name, "NXpositioner", parentclasses=("NXinstrument",), **kwargs
    )


def nxData(parent, name, **kwargs):
    """
    Get NXdata instance (initialize when missing)

    :param h5py.Group parent:
    :param str or None name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    if name is None:
        name = DEFAULT_PLOT_NAME
    return nxClassInit(parent, name, "NXdata", **kwargs)


def nxDataGetSignals(data):
    """
    Get NXdata signals (default signal first)

    :param h5py.Group data:
    :returns list(str): signal names (default first)
    """
    signal = attr_as_str(data, "signal", None)
    auxsignals = attr_as_str(data, "auxiliary_signals", None)
    if signal is None:
        lst = []
    else:
        lst = [signal]
    if auxsignals is not None:
        lst += auxsignals.tolist()
    return lst


def nxDataSetSignals(data, signals):
    """
    Set NXdata signals (default signal first)

    :param h5py.Group data:
    :param list(str) signals:
    """
    if signals:
        updateAttribute(data, "signal", signals[0])
        if len(signals) > 1:
            updateAttribute(data, "auxiliary_signals", asNxChar(signals[1:]))
        else:
            data.attrs.pop("auxiliary_signals", None)
    else:
        data.attrs.pop("signal", None)
        data.attrs.pop("auxiliary_signals", None)
    updated(data)


def _datasetMergeInfo(
    uris,
    shape=None,
    dtype=None,
    axis=0,
    newaxis=True,
    order=None,
    fill_generator=None,
    virtual_source_args=None,
):
    """
    Equivalent to `numpy.stack` or `numpy.concatenate` combined
    with `numpy.reshape`. Return I/O index generator for merging.

    :param list(str) uris:
    :param tuple shape:
    :param dtype dtype:
    :param int axis:
    :param bool newaxis:
    :param str order: for reshaping
    :param fill_generator:
    :returns tuple, dtype, generator: merged shape
                                      merged dtype
                                      uri I/O index generator
    """
    if not isinstance(uris, (tuple, list)):
        uris = [uris]
    if virtual_source_args:
        dtypes = {virtual_source_args["dtype"]}
        shapei = virtual_source_args["shape"]
        shapes = [shapei] * len(uris)
        ushapes = {shapei}
    else:
        shapes = []
        ushapes = []
        dtypes = set()
        for uri in uris:
            with uriContext(uri, mode="r") as dset:
                dtypes.add(dset.dtype)
                shapei = dset.shape
                shapes.append(shapei)
                shapei = list(shapei)
                try:
                    shapei[axis] = None
                except IndexError:
                    pass
                ushapes.append(tuple(shapei))
    if len(set(ushapes)) > 1:
        raise RuntimeError("Cannot concatenate datasets with shapes {}".format(ushapes))
    # Merged dtype
    if dtype is None:
        dtype = sum(numpy.array(0, dtype=dt) for dt in dtypes).dtype
    # Generator for source->destination filling
    if fill_generator is None:
        shape, fill_generator = data_merging.mergeGenerator(
            uris,
            shapes,
            shape=shape,
            order=order,
            axis=axis,
            newaxis=newaxis,
            allow_advanced_indexing=False,
        )
    elif shape is None:
        raise ValueError("Specify 'shape' when specifying 'fill_generator'")
    return shape, dtype, fill_generator


def createVirtualDataset(
    h5group,
    name,
    uris,
    axis=0,
    newaxis=True,
    maxshape=None,
    fillvalue=None,
    shape=None,
    dtype=None,
    order=None,
    fill_generator=None,
    virtual_source_args=None,
):
    """
    Create a virtual dataset (references to the individual datasets)

    :param h5py.Group h5group: parent
    :param str name:
    :param list(str) uris:
    :param int axis:
    :param bool newaxis:
    :param tuple maxshape:
    :param fillvalue:
    :param dtype:
    :param str order: for reshaping
    :param fill_generator:
    :param dict virtual_source_args: arguments for VirtualSource (avoid opening the source files)
    :returns h5py.Dataset:
    """
    shape, dtype, fill_generator = _datasetMergeInfo(
        uris,
        shape=shape,
        dtype=dtype,
        axis=axis,
        order=order,
        newaxis=newaxis,
        fill_generator=fill_generator,
        virtual_source_args=virtual_source_args,
    )
    layout = h5py.VirtualLayout(shape, dtype=dtype, maxshape=maxshape)
    destination = splitUri(getUri(h5group))
    if virtual_source_args:
        logger.debug("Create VDS {} without opening sources".format(repr(destination)))
        for uri, idx_generator in fill_generator():
            source = splitUri(uri)
            spath, sname = relUri(source, destination)
            # TODO: VirtualSource does not support relative
            #       file paths upwards
            if ".." in spath:
                spath, sname = source
            # TODO: VirtualSource does not support relative
            #       dataset paths like SoftLink
            sname = source[1]
            vsource = h5py.VirtualSource(spath, sname, **virtual_source_args)
            for idxin, idxout in idx_generator():
                if idxin:
                    layout[idxout] = vsource[idxin]
                else:
                    layout[idxout] = vsource
                gevent.sleep()
    else:
        logger.debug("Create VDS {} with opening sources".format(repr(destination)))
        for uri, idx_generator in fill_generator():
            source = splitUri(uri)
            spath, sname = relUri(source, destination)
            with uriContext(uri, mode="r") as dset:
                # TODO: VirtualSource does not support relative
                #       file paths upwards
                if ".." in spath:
                    spath, sname = source
                # TODO: VirtualSource does not support relative
                #       dataset paths like SoftLink
                sname = source[1]
                vsource = h5py.VirtualSource(
                    spath,
                    sname,
                    shape=dset.shape,
                    dtype=dset.dtype,
                    maxshape=dset.maxshape,
                )
                for idxin, idxout in idx_generator():
                    if idxin:
                        layout[idxout] = vsource[idxin]
                    else:
                        layout[idxout] = vsource
                    gevent.sleep()
    return h5group.create_virtual_dataset(name, layout, fillvalue=fillvalue)


def createConcatenatedDataset(
    h5group,
    name,
    uris,
    axis=0,
    newaxis=True,
    shape=None,
    dtype=None,
    order=None,
    fill_generator=None,
    **kwargs,
):
    """
    Create a concatenated dataset (copy of the individual datasets)

    :param h5py.Group h5group: parent
    :param str name:
    :param list(str) uris:
    :param int axis:
    :param bool newaxis:
    :param dtype:
    :param str order: for reshaping
    :param fill_generator:
    :returns h5py.Dataset:
    """
    shape, dtype, fill_generator = _datasetMergeInfo(
        uris,
        shape=shape,
        dtype=dtype,
        order=order,
        axis=axis,
        newaxis=newaxis,
        fill_generator=fill_generator,
    )
    kwargs["shape"] = shape
    kwargs["dtype"] = dtype
    dset = h5group.create_dataset(name, **kwargs)
    for uri, index_generator in fill_generator():
        with uriContext(uri, mode="r") as dseti:
            for idxin, idxout in index_generator():
                dset[idxout] = dseti[idxin]
                gevent.sleep()
    return dset


def createMergedDataset(h5group, name, uris, virtual=True, **kwargs):
    """
    Merge datasets into one dataset

    :param h5py.Group h5group: parent
    :param str name:
    :param list(str) uris:
    :param bool virtual: merge as virtual dataset (copy otherwise)
    :param **kwargs:
    :returns h5py.Dataset:
    """
    if not HASVIRTUAL:
        logger.warning(
            "Virtual HDF5 datasets are not supported: concatenate instead (this creates a copy)."
        )
        virtual = False
    if virtual:
        return createVirtualDataset(h5group, name, uris, **kwargs)
    else:
        return createConcatenatedDataset(h5group, name, uris, **kwargs)


def vdsmapUri(dset, vdsmap):
    """
    :param Dataset dset:
    :param VDSmap vdsmap:
    :returns str:
    """
    filename = vdsmap.file_name
    if not os.path.isabs(filename):
        path = os.path.dirname(dset.file.filename)
        if filename == ".":
            filename = os.path.basename(dset.file.filename)
        filename = os.path.join(path, filename)
    return filename + "::" + vdsmap.dset_name


def vdsmapIsValid(dset, vdsmap):
    """
    :param Dataset dset:
    :param VDSmap vdsmap:
    :returns bool:
    """
    return exists(vdsmapUri(dset, vdsmap))


def vdsIsValid(dset):
    """
    :param Dataset dset:
    :returns bool:
    """
    if not dset.is_virtual:
        raise ValueError("Not a virtual dataset")
    sources = dset.virtual_sources()
    if not sources:
        shape = dset.shape
        return not shape or not all(shape)
    for vdsmap in sources:
        if not vdsmapIsValid(dset, vdsmap):
            return False
    return True


def createLink(h5group, name, destination, abspath=False):
    """
    Create hdf5 soft (supports relative down paths)
    or external link (supports relative paths).

    :param h5py.Group h5group: location of the link
    :param str name:
    :param str or h5py.Dataset destination:
    :param bool abspath: absolute file path
    :returns: h5py link object
    """
    if not isinstance(destination, (str, bytes)):
        destination = getUri(destination)
    if "::" in destination:
        destination = splitUri(destination)
    else:
        destination = h5group.file.filename, destination
    filename, path = destination
    lnk_filename, lnk_path = relUri(destination, getUri(h5group))
    if lnk_filename == ".":
        # TODO: h5py.SoftLink does not support relative links upwards
        if ".." in lnk_path:
            lnk_path = path
        lnk = h5py.SoftLink(lnk_path)
    else:
        if abspath:
            lnk_filename = filename
        lnk = h5py.ExternalLink(lnk_filename, lnk_path)
    h5group[name] = lnk
    return lnk


def nxCreateDataSet(h5group, name, value, attrs, stringasuri=False):
    """
    Create a dataset or a link to a dataset

    :param h5py.Group h5group: parent
    :param str name: dataset name
    :param value: None: do not create dataset
                  str: create link to uri when `stringasuri==True`
                  h5py.Dataset: create link
                  dict: `isinstance(dict['data'], h5py.Dataset)`: soft or external link
                        `'axis' in dict`: merge uris in `dict['data']`
                        else: h5py.create_dataset arguments
                  other (numpy.ndarray, num, ...): data content
    :param dict attrs: set as dataset attributes
    :param str stringasuri: interpret string as a dataset uri
    :returns h5py.Dataset:
    """
    if stringasuri:
        dsettypes = (h5py.Dataset, str, bytes)
    else:
        dsettypes = (h5py.Dataset,)
    if isinstance(value, dict):
        data = value.get("data", None)
        merge = any(
            k in value for k in ["axis", "newaxis", "virtual", "fill_generator"]
        )
        if not merge:
            if isinstance(data, dsettypes):
                # dataset or uri
                shape = value.get("shape", None)
                # TODO: dtype, maxshape as well?
                # merge when attributes do not match the existing dataset
                if isinstance(data, h5py.Dataset):
                    merge = shape != data.shape
                else:
                    with uriContext(data) as dset:
                        if dset is not None:
                            merge = shape != dset.shape
                # link when attributes match the existing dataset
                if not merge:
                    value = data
            else:
                value["data"] = asNxType(data)
    if value is None:
        # dataset exists already or will be created elsewhere
        pass
    elif isinstance(value, dsettypes):
        # link to dataset
        logger.debug(
            "Create HDF5 dataset {}/{}: link to {}".format(getUri(h5group), name, value)
        )
        createLink(h5group, name, value)
    elif isinstance(value, dict):
        # create dataset (internal, external, virtual) with extra options
        if merge:
            value = dict(value)
            axis = value.pop("axis", 0)
            uris = value.pop("data", [])
            logger.debug("Create HDF5 dataset {}/{}".format(getUri(h5group), name))
            createMergedDataset(h5group, name, uris, axis=axis, **value)
        else:
            # TODO: external datasets do not support relative paths
            # external = value.get('external', None)
            # if external:
            #    dirname = os.path.dirname(h5group.file.filename)
            #    value['external'] = [(os.path.relpath(tpl[0], dirname),) + tpl[1:]
            #                         for tpl in external]
            logger.debug("Create HDF5 dataset {}/{}".format(getUri(h5group), name))
            createNxValidate(value)
            h5group.create_dataset(name, **value)
    else:
        # create dataset (internal) without extra options
        logger.debug("Create HDF5 dataset {}/{}".format(getUri(h5group), name))
        h5group[name] = asNxType(value)
    dset = h5group.get(name, None)
    if attrs and dset is not None:
        for k, v in attrs.items():
            updateAttribute(dset, k, v)
    return dset


def nxDatasetInterpretation(scan_ndim, detector_ndim, dataset_ndim):
    """
    Dataset interpretation

    :param int scan_ndim: scan dimensions
    :param int detector_ndim: detector data
    :param int dataset_ndim: as saved (scan_ndim may be flattened)
    """
    if detector_ndim == 0:
        if scan_ndim == dataset_ndim:
            # Scan dimension is not flattened
            if scan_ndim == 2:
                return "image"
            elif scan_ndim == 3:
                return "vertex"
    elif detector_ndim == 1:
        return "spectrum"
    elif detector_ndim == 2:
        return "image"
    elif detector_ndim == 3:
        return "vertex"
    return None


def nxDataAddSignals(data, signals, append=True):
    """
    Add signals to NXdata instance

    :param h5py.Group data:
    :param list(3-tuple) signals: see `nxCreateDataSet`
    :param bool append:
    """
    raiseIsNotNxClass(data, "NXdata")
    if append:
        names = nxDataGetSignals(data)
    else:
        names = []
    for name, value, attrs in signals:
        nxCreateDataSet(data, name, value, attrs, stringasuri=True)
        if name not in names:
            names.append(name)
    if names:
        nxDataSetSignals(data, names)


def nxDataAddAxes(data, axes, append=True):
    """
    Add axes to NXdata instance

    :param h5py.Group data: NXdata instance
    :param list(3-tuple) axes: see `nxCreateDataSet`
    :param bool append:
    """
    raiseIsNotNxClass(data, "NXdata")
    if append:
        names = attr_as_str(data, "axes", [])
    else:
        names = []
    for name, value, attrs in axes:
        nxCreateDataSet(data, name, value, attrs, stringasuri=True)
        if name not in names:
            names.append(name)
    if names:
        updateAttribute(data, "axes", asNxChar(names))
        updated(data)


def nxDataAddErrors(data, errors):
    """
    For each dataset in "data", link to the corresponding dataset in "errors".

    :param h5py.Group data:
    :param h5py.Group errors:
    """
    for name in data:
        dest = errors.get(name, None)
        if dest:
            data[name + "_errors"] = h5py.SoftLink(dest.name)


def selectDatasets(root, match=None):
    """
    Select datasets with given restrictions. In case of `root`
    is an NXdata instance, an additional restriction is imposed:
    the dataset must be specified as a signal (including auxilary signals).

    :param h5py.Group or h5py.Dataset root:
    :param match: restrict selection (callable, 'max_ndim', 'mostcommon_ndim')
    :returns list(h5py.Dataset):
    """
    if match == "max_ndim":
        match, post = None, match
    elif match == "mostcommon_ndim":
        match, post = None, match
    else:
        post = None
    if not match:

        def match(dset):
            return True

    datasets = []
    if isinstance(root, h5py.Dataset):
        if match(root):
            datasets = [root]
    else:
        labels = nxDataGetSignals(root)
        if not labels:
            labels = root.keys()
        for label in labels:
            dset = root.get(label, None)
            if not isinstance(dset, h5py.Dataset):
                continue
            if match(dset):
                datasets.append(dset)
        if post == "max_ndim":
            ndimref = max(dset.ndim for dset in datasets)
        elif post == "mostcommon_ndim":
            occurences = Counter(dset.ndim for dset in datasets)
            ndimref = occurences.most_common(1)[0][0]
        else:
            ndimref = None
        if ndimref is not None:
            datasets = [dset.ndim == ndimref for dset in datasets]
    return datasets


def markDefault(h5node, nxentrylink=True):
    """
    Mark HDF5 Dataset or Group as default (parents get notified as well)

    :param h5py.Group or h5py.Dataset h5node:
    :param bool nxentrylink: Use a direct link for the default of an NXentry instance
    """
    nxdata = None
    nxclass = nxClass(h5node)
    for parent in iterup(h5node, includeself=False):
        parentnxclass = nxClass(parent)
        if parentnxclass == "NXdata":
            signals = nxDataGetSignals(parent)
            signal = h5Name(h5node)
            if signal in signals:
                signals.pop(signals.index(signal))
            nxDataSetSignals(parent, [signal] + signals)
            updated(parent)
        elif nxclass in ["NXentry", "NXsubentry"]:
            updateAttribute(parent, "default", h5Name(h5node))
            updated(parent)
        elif nxclass == "NXdata":
            updateAttribute(parent, "default", h5Name(h5node))
            updated(parent)
            nxdata = h5node
        else:
            updateAttribute(parent, "default", h5Name(h5node))
            updated(parent)
        h5node = parent
        nxclass = parentnxclass
    if nxdata is not None:
        _nxentry_plot_link(nxdata)


def _nxentry_plot_link(nxdata):
    for nxentry in iterup(nxdata, includeself=False):
        if isNxClass(nxentry, "NXentry"):
            break
    else:
        return
    plotname = DEFAULT_PLOT_NAME
    if isLink(nxentry, plotname):
        del nxentry[plotname]
    if plotname in nxentry:
        if nxentry[plotname].name == nxdata.name:
            return
        fmt = plotname + "{}"
        i = 0
        while fmt.format(i) in nxentry:
            i += 1
        plotname = fmt.format(i)
    nxentry[plotname] = h5py.SoftLink(nxdata.name)
    updateAttribute(nxentry, "default", plotname)


def getDefault(node, signal=True):
    """
    :param h5py.Group or h5py.Dataset node:
    :returns str: path of dataset or NXdata group
    """
    default = attr_as_str(node, "default", "")
    root = node.file
    if default and not default.startswith("/"):
        if node.name == "/":
            default = "/" + default
        else:
            default = node.name + "/" + default
    while default:
        try:
            node = root[default]
        except KeyError:
            break
        nxclass = attr_as_str(node, "NX_class", "")
        if nxclass == "NXdata":
            if signal:
                name = attr_as_str(node, "signal", "data")
                try:
                    default = node[name].name
                except KeyError:
                    pass
            else:
                default = node.name
            break
        else:
            add = attr_as_str(node, "default", "")
            if add.startswith("/"):
                default = add
            elif add:
                default += "/" + add
            else:
                break
    return default


def getDefaultUri(filename, signal=True, **kwargs):
    """
    :param str filename:
    :returns str: full uri to default data
    """
    with File(filename, **kwargs) as f:
        path = getDefault(f, signal=signal)
    if path:
        return filename + "::" + path
    else:
        return None
