# -*- coding: utf-8 -*-
#
# This file is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Nexus API
"""

import h5py
import time
import datetime
import numpy
import os
import re
import pprint
import logging
import bliss
from functools import wraps
from io import StringIO
from collections import Counter
from contextlib import contextmanager
from silx.io.dictdump import dicttojson, dicttoini
from .io_utils import mkdir
from ..utils import data_merging


DEFAULT_PLOT_NAME = "plotselect"


try:
    unicode
except NameError:
    unicode = str


try:
    h5py.VirtualLayout
except AttributeError:
    HASVIRTUAL = False
else:
    HASVIRTUAL = True
HASSWMR = h5py.version.hdf5_version_tuple >= (1, 10)


logger = logging.getLogger(__name__)


nxcharUnicode = h5py.special_dtype(vlen=unicode)
nxcharBytes = h5py.special_dtype(vlen=bytes)


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
    try:
        # dtype=nxcharUnicode will not attempt decoding bytes
        # so readers will get UnicodeDecodeError when bytes
        # are extended ASCII encoded. So do this instead:
        numpy.array(s, dtype=unicode)
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


class LocalTZinfo(datetime.tzinfo):

    _offset = datetime.timedelta(seconds=-time.altzone)
    _dst = datetime.timedelta(0)
    _name = time.tzname[time.daylight]

    def utcoffset(self, dt):
        return self.__class__._offset

    def dst(self, dt):
        return self.__class__._dst

    def tzname(self, dt):
        return self.__class__._name

    def localize(self, dt):
        if dt.tzinfo is not None:
            raise ValueError("Not naive datetime (tzinfo is already set)")
        return dt.replace(tzinfo=self)


def datetime_to_nexus(tm):
    """
    Format datetime for Nexus saving

    :param datetime.datetime tm:
    :returns np.ndarray: variable length string
    """
    if tm.tzinfo is None:
        tm = LocalTZinfo().localize(tm)
    return asNxChar(tm.isoformat())


def timestamp():
    """
    Timestamp for Nexus saving

    :returns np.ndarray: variable length string
    """
    return datetime_to_nexus(datetime.datetime.now(tz=LocalTZinfo()))


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
    """
    Normalize uri

    :param str uri: URI
    :return str:
    """
    filename, path = splitUri(uri)
    filename = os.path.normpath(filename)
    path = hdf5_normpath(path)
    return filename + "::" + path


def dereference(node):
    """
    :param h5py.Dataset or h5py.Group:
    :returns str: uri
    """
    if node.name == "/":
        return getUri(node)
    try:
        lnk = node.parent.get(node.name, default=None, getlink=True)
    except (KeyError, RuntimeError):
        return getUri(node)
    else:
        if isinstance(lnk, h5py.SoftLink):
            path = lnk.path
            if not path.startswith("/"):
                path = hdf5_join(node.parent.name, path)
            return node.file.filename + "::" + hdf5_normpath(path)
        elif isinstance(lnk, h5py.ExternalLink):
            return lnk.filename + "::" + lnk.path
        else:
            return getUri(node)


def dereferenceUri(uri):
    """
    Get full URI of dataset or group

    :param h5py.Dataset or h5py.Group:
    :returns str:
    """
    filename, path = splitUri(uri)
    uri2 = uri
    istart = 1
    with h5open(filename, mode="r") as f:
        while True:
            parts = path.split("/")[1:]
            for i in range(istart, len(parts) + 1):
                path2 = hdf5_join(*parts[:i])
                filename2, path2 = splitUri(dereference(f[path2]))
                path2 = hdf5_join(path2, *parts[i:])
                uri2 = filename2 + "::" + path2
                if uri != uri2:
                    if filename == filename2:
                        path = path2
                        istart = i + 1
                        break
                    else:
                        return dereferenceUri(uri2)
            else:
                break
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
        with h5open(filename, **kwargs) as f:
            yield f[path]
    except (OSError, IOError, KeyError):
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
    except (OSError, IOError, KeyError):
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
        return v.encode()
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
        raise RuntimeError("Nexus class not in {}".format(classes))


def raiseIsNotNxClass(h5group, *classes):
    """
    :param h5py.Group h5group:
    :param *classes: list(str) of Nexus classes
    :raises RuntimeError:
    """
    if not isNxClass(h5group, *classes):
        raise RuntimeError("Nexus class not in {}".format(classes))


def nxClassNeedsInit(parent, name, nxclass):
    """
    Check whether parent[name] needs Nexus initialization

    :param h5py.Group parent:
    :param str or None name:
    :param str nxclass:
    :returns bool: needs initialization
    :raises RuntimeError: wrong Nexus class
    """
    if name is None:
        return nxclass != nxClass(parent)
    if name in parent:
        _nxclass = nxClass(parent[name])
        if _nxclass != nxclass:
            raise RuntimeError(
                "{} is an instance of {} instead of {}".format(
                    parent[name].name, nxclass, _nxclass
                )
            )
        return False
    else:
        parent.create_group(name)
        return True


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
        elif nxclass in [u"NXentry", u"NXsubentry"]:
            if "start_time" not in group:
                group["start_time"] = tm
            if final:
                updateDataset(group, "end_time", tm)
        elif nxclass in [u"NXprocess", u"NXnote"]:
            updateDataset(group, "date", tm)
        elif nxclass == u"NXroot":
            group.attrs["file_update_time"] = tm
        if not parents:
            break


def updateDataset(parent, name, data):
    """
    :param h5py.Group parent:
    :param str name:
    :param data:
    """
    if isinstance(data, (unicode, bytes)):
        data = asNxChar(data)
    if name in parent:
        parent[name][()] = data
    else:
        parent[name] = data


def nxClassInit(parent, name, nxclass, parentclasses=None, **kwargs):
    """
    Initialize Nexus class instance without default attributes and datasets

    :param h5py.Group parent:
    :param str name:
    :param str nxclass:
    :param tuple parentclasses:
    :param **kwargs: see `nxInit`
    :raises RuntimeError: wrong Nexus class or parent
                          not an Nexus class instance
    """
    if parentclasses:
        raiseIsNotNxClass(parent, *parentclasses)
    else:
        raiseIsNxClass(parent, None)
    if nxClassNeedsInit(parent, name, nxclass):
        h5group = parent[name]
        nxAddAttrInit(kwargs, "NX_class", nxclass)
        nxInit(h5group, **kwargs)
        updated(h5group)


def nxRootInit(h5group):
    """
    Initialize NXroot instance

    :param h5py.Group h5group:
    :raises ValueError: not root
    :raises RuntimeError: wrong Nexus class
    """
    if h5group.name != "/":
        raise ValueError("Group should be the root")
    if nxClassNeedsInit(h5group, None, u"NXroot"):
        h5group.attrs["file_time"] = timestamp()
        h5group.attrs["file_name"] = asNxChar(h5group.file.filename)
        h5group.attrs["HDF5_Version"] = asNxChar(h5py.version.hdf5_version)
        h5group.attrs["h5py_version"] = asNxChar(h5py.version.version)
        h5group.attrs["creator"] = asNxChar("bliss")
        h5group.attrs["NX_class"] = u"NXroot"
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
        h5group.attrs.update(attrs)


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


def _nxEntryInit(parent, name, sub=False, start_time=None, **kwargs):
    """
    Initialize NXentry and NXsubentry instance

    :param h5py.Group parent:
    :param bool sub:
    :param datetime start_time: 'now' when missing
    :param **kwargs: see `nxInit`
    :raises RuntimeError: wrong NX_class or parent NX_class
    """
    if sub:
        nxclass = u"NXsubentry"
        parents = (u"NXentry",)
    else:
        nxclass = u"NXentry"
        parents = (u"NXroot",)
    raiseIsNotNxClass(parent, *parents)
    if nxClassNeedsInit(parent, name, nxclass):
        h5group = parent[name]
        if start_time is None:
            start_time = timestamp()
        else:
            start_time = datetime_to_nexus(start_time)
        nxAddDatasetInit(kwargs, "start_time", start_time)
        nxAddAttrInit(kwargs, "NX_class", nxclass)
        nxInit(h5group, **kwargs)
        updated(h5group)


def nxEntryInit(parent, name, **kwargs):
    """
    Initialize NXentry instance

    :param h5py.Group parent:
    :param datetime start_time: 'now' when missing
    :param **kwargs: see `nxInit`
    :raises RuntimeError: wrong NX_class or parent not NXroot
    """
    _nxEntryInit(parent, name, sub=False, **kwargs)


def nxSubEntryInit(parent, name, **kwargs):
    """
    Initialize NXsubentry instance

    :param h5py.Group parent:
    :param datetime start_time: 'now' when missing
    :param **kwargs: see `_nxEntryInit`
    :raises RuntimeError: wrong NX_class or parent not NXentry
    """
    _nxEntryInit(parent, name, sub=True, **kwargs)


def nxNoteInit(parent, name, data=None, type=None):
    """
    Initialize NXnote instance

    :param h5py.Group parent:
    :param str name:
    :param str data:
    :param str type:
    :raises RuntimeError: wrong Nexus class or parent
                          not an Nexus class instance
    """
    raiseIsNxClass(parent, None)
    if nxClassNeedsInit(parent, name, u"NXnote"):
        h5group = parent[name]
        h5group.attrs["NX_class"] = u"NXnote"
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
    if update:
        updated(h5group)


def nxProcessConfigurationInit(parent, configdict=None, type="json", indent=2):
    """
    Initialize NXnote instance

    :param h5py.Group parent:
    :param dict configdict:
    :param str type: 'json' or 'ini' or None (pprint)
    :param num indent: pretty-string with indent level
    :raises RuntimeError: parent not NXprocess
    """
    raiseIsNotNxClass(parent, u"NXprocess")
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
    name = "configuration"
    nxNoteInit(parent, name, data=data, type=type)
    updated(parent[name])


def nxProcessInit(parent, name, configdict=None, **kwargs):
    """
    Initialize NXprocess instance

    :param h5py.Group parent:
    :param str name:
    :param dict configdict:
    :param **kwargs: see `nxProcessConfigurationInit`
    :raises RuntimeError: wrong Nexus class or parent not NXentry
    """
    raiseIsNotNxClass(parent, u"NXentry")
    if nxClassNeedsInit(parent, name, u"NXprocess"):
        h5group = parent[name]
        updateDataset(h5group, "program", "bliss")
        updateDataset(h5group, "version", bliss.__version__)
        h5group.attrs["NX_class"] = u"NXprocess"
        updated(h5group)
    else:
        h5group = parent[name]
    nxProcessConfigurationInit(h5group, configdict=configdict, **kwargs)
    nxClassInit(h5group, "results", u"NXcollection")


@contextmanager
def _h5file(path, creationlocks=None, mode="r", **kwargs):
    """
    HDF5 file context with creation locking

    :param str path:
    :param str mode:
    :param SharedLockPool creationlocks:
    :param **kwargs: see h5py.File
    :yields h5py.File:
    """
    if creationlocks is None:
        with h5py.File(path, mode=mode, **kwargs) as h5file:
            yield h5file
    else:
        with creationlocks.acquire_context_creation(
            path, h5py.File, path, mode=mode, **kwargs
        ) as h5file:
            yield h5file


@contextmanager
def h5open(path, mode="r", enable_file_locking=False, swmr=False, **kwargs):
    """
    HDF5 file context which does not lock the file by default.
    When file locking is enabled, you can have a single writer
    and multiple readers when the writer contexts has `swmr=True`:

    .. code-block:: python

        with h5open('test.h5', mode='a', swmr=True, enable_file_locking=True):
            ...

        with h5open('test.h5', mode='r', enable_file_locking=True):
            ...

        with h5open('test.h5', mode='r', enable_file_locking=True):
            ...

        ...

    :param str path:
    :param str mode:
    :param bool enable_file_locking: locking is done in all modes
                                     (also read-only).
    :param bool swmr: files locked with `swmr=True` and `mode!='r'`
                      can be opened read-only but modifications
                      to the file will not be visible.
    :param **kwargs: see `_h5file`
    :yields h5py.File:
    """
    # https://support.hdfgroup.org/HDF5/docNewFeatures/SWMR/Design-HDF5-FileLocking.pdf
    if not HASSWMR:
        swmr = False
    if swmr:
        kwargs["libver"] = "latest"
    if enable_file_locking:
        os.environ["HDF5_USE_FILE_LOCKING"] = "TRUE"
    else:
        os.environ["HDF5_USE_FILE_LOCKING"] = "FALSE"
    try:
        with _h5file(path, mode=mode, swmr=swmr, **kwargs) as h5file:
            if mode != "r" and swmr:
                try:
                    h5file.swmr_mode = True
                except Exception:
                    pass
            yield h5file
    except (OSError, IOError):
        if mode != "r" and not HASSWMR:
            raise
        # Try opposite SWMR mode
        swmr = not swmr
        if swmr:
            kwargs["libver"] = "latest"
        with _h5file(path, mode=mode, swmr=swmr, **kwargs) as h5file:
            yield h5file


@contextmanager
def nxRoot(path, mode="r", creationlocks=None, **kwargs):
    """
    h5py.File context with NXroot initialization

    :param str path:
    :param str mode: h5py.File modes
    :param geventsync.SharedLockPool creationlocks: protect creation
    :param **kwargs: see h5py.File
    :yields h5py.File:
    """
    if mode != "r":
        mkdir(os.path.dirname(path))
    with h5open(path, mode=mode, creationlocks=creationlocks, **kwargs) as h5file:
        if creationlocks is None:
            nxRootInit(h5file)
        else:
            with creationlocks.acquire(path):
                nxRootInit(h5file)
        yield h5file


def nxEntry(root, name, **kwargs):
    """
    Get NXentry instance (initialize when missing)

    :param h5py.Group root:
    :param str name:
    :param **kwargs: see `nxEntryInit`
    :returns h5py.Group:
    """
    nxEntryInit(root, name, **kwargs)
    return root[name]


def nxSubEntry(parent, name, **kwargs):
    """
    Get NXsubentry instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxSubEntryInit`
    :returns h5py.Group:
    """
    nxSubEntryInit(parent, name, **kwargs)
    return parent[name]


def nxProcess(entry, name, **kwargs):
    """
    Get NXprocess instance (initialize when missing)

    :param h5py.Group entry:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    nxProcessInit(entry, name, **kwargs)
    return entry[name]


def nxCollection(parent, name, **kwargs):
    """
    Get NXcollection instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    nxClassInit(parent, name, u"NXcollection", **kwargs)
    return parent[name]


def nxInstrument(parent, name="instrument", **kwargs):
    """
    Get NXinstrument instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    nxClassInit(parent, name, u"NXinstrument", parentclasses=(u"NXentry",), **kwargs)
    return parent[name]


def nxDetector(parent, name, **kwargs):
    """
    Get NXdetector instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    nxClassInit(parent, name, u"NXdetector", parentclasses=(u"NXinstrument",), **kwargs)
    return parent[name]


def nxPositioner(parent, name, **kwargs):
    """
    Get NXpositioner instance (initialize when missing)

    :param h5py.Group parent:
    :param str name:
    :param **kwargs: see `nxClassInit`
    :returns h5py.Group:
    """
    nxClassInit(
        parent, name, u"NXpositioner", parentclasses=(u"NXinstrument",), **kwargs
    )
    return parent[name]


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
    nxClassInit(parent, name, u"NXdata", **kwargs)
    return parent[name]


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
        data.attrs["signal"] = asNxChar(signals[0])
        if len(signals) > 1:
            data.attrs["auxiliary_signals"] = asNxChar(signals[1:])
        else:
            data.attrs.pop("auxiliary_signals", None)
    else:
        data.attrs.pop("signal", None)
        data.attrs.pop("auxiliary_signals", None)
    updated(data)


def _datasetMergeInfo(
    uris, shape=None, dtype=None, axis=0, newaxis=True, order=None, fill_generator=None
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
    shapes = []
    ushapes = []
    dtypes = set()
    if not isinstance(uris, (tuple, list)):
        uris = [uris]
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
    )
    layout = h5py.VirtualLayout(shape, dtype=dtype, maxshape=maxshape)
    destination = splitUri(getUri(h5group))
    for uri, idx_generator in fill_generator():
        source = splitUri(uri)
        spath, sname = relUri(source, destination)
        with uriContext(uri, mode="r") as dset:
            if ".." in spath:
                spath, sname = source
            # TODO: VirtualSource does not support relative
            #       dataset paths like SoftLink
            sname = source[1]
            vsource = h5py.VirtualSource(
                spath, sname, shape=dset.shape, dtype=dset.dtype, maxshape=dset.maxshape
            )
            for idxin, idxout in idx_generator():
                if idxin:
                    layout[idxout] = vsource[idxin]
                else:
                    layout[idxout] = vsource
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
    **kwargs
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


def createLink(h5group, name, destination):
    """
    Create hdf5 soft (supports relative down paths)
    or external link (supports relative paths).

    :param h5py.Group h5group: location of the link
    :param str name:
    :param str or h5py.Dataset destination:
    :returns: h5py link object
    """
    if not isinstance(destination, (unicode, bytes)):
        destination = getUri(destination)
    destination = splitUri(destination)
    filename, path = relUri(destination, getUri(h5group))
    if filename == ".":
        # TODO: h5py does not support relative up links
        if ".." in path:
            path = destination[1]
        h5group[name] = h5py.SoftLink(path)
    else:
        h5group[name] = h5py.ExternalLink(filename, path)
    return h5group[name]


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
        dsettypes = (h5py.Dataset, unicode, bytes)
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
            elif isinstance(data, (unicode, bytes)):
                # dataset of string type
                value["data"] = asNxChar(data)
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
            logger.debug(
                "Create HDF5 dataset {}/{}: merge {}".format(
                    getUri(h5group), name, uris
                )
            )
            createMergedDataset(h5group, name, uris, axis=axis, **value)
        else:
            # TODO: external datasets do not support relative paths
            # external = value.get('external', None)
            # if external:
            #    dirname = os.path.dirname(h5group.file.filename)
            #    value['external'] = [(os.path.relpath(tpl[0], dirname),) + tpl[1:]
            #                         for tpl in external]
            logger.debug("Create HDF5 dataset {}/{}".format(getUri(h5group), name))
            h5group.create_dataset(name, **value)
    else:
        # create dataset (internal) without extra options
        if isinstance(value, (unicode, bytes)):
            value = asNxChar(value)
        logger.debug("Create HDF5 dataset {}/{}".format(getUri(h5group), name))
        h5group[name] = value
    dset = h5group.get(name, None)
    if attrs and dset is not None:
        attrs = {k: v for k, v in attrs.items() if v is not None}
        dset.attrs.update(attrs)
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
    raiseIsNotNxClass(data, u"NXdata")
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
    raiseIsNotNxClass(data, u"NXdata")
    if append:
        names = attr_as_str(data, "axes", [])
    else:
        names = []
    for name, value, attrs in axes:
        nxCreateDataSet(data, name, value, attrs, stringasuri=True)
        if name not in names:
            names.append(name)
    if names:
        data.attrs["axes"] = asNxChar(names)
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
    path = h5node
    nxclass = nxClass(path)
    nxdata = None
    for parent in iterup(path.parent):
        parentnxclass = nxClass(parent)
        if parentnxclass == u"NXdata":
            # path becomes default signal of parent
            signals = nxDataGetSignals(parent)
            signal = h5Name(path)
            if signal in signals:
                signals.pop(signals.index(signal))
            nxDataSetSignals(parent, [signal] + signals)
            updated(parent)
        elif nxclass == u"NXentry":
            # Set this entry as default of root
            parent.attrs["default"] = h5Name(path)
            updated(parent)
        elif parentnxclass is not None:
            if nxclass == u"NXdata":
                # Select the NXdata for plotting
                nxdata = path
            if nxdata:
                if parentnxclass == u"NXentry" and nxentrylink:
                    # Instead of setting the default of parent to the selected NXdata,
                    # create a direct link to the select NXData and set that link as
                    # default of the parent
                    plotname = DEFAULT_PLOT_NAME
                    if isLink(parent, plotname):
                        # parent already has plotname: delete because its merely a link
                        del parent[plotname]
                    if plotname in parent:
                        # parent already has plotname: find non-existent plotname
                        # unless plotname is the selected NXdata, in which case
                        # nothing has to be done
                        if parent[plotname].name != nxdata.name:
                            fmt = plotname + "{}"
                            i = 0
                            while fmt.format(i) in parent:
                                i += 1
                            plotname = fmt.format(i)
                            parent[plotname] = h5py.SoftLink(nxdata.name)
                    else:
                        parent[plotname] = h5py.SoftLink(nxdata.name)
                    parent.attrs["default"] = plotname
                else:
                    # Set default of parent to the selected NXdata
                    parent.attrs["default"] = nxdata.name[len(parent.name) + 1 :]
                updated(parent)
            if parentnxclass == u"NXroot":
                break
        path = parent
        nxclass = parentnxclass


def getDefault(node, signal=True):
    """
    :param h5py.Group or h5py.Dataset h5node:
    :returns str: path of dataset or NXdata group
    """
    path = ""
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
                    path = node[name].name
                except KeyError:
                    pass
            else:
                path = node.name
            break
        else:
            add = attr_as_str(node, "default", "")
            if add.startswith("/"):
                default = add
            elif add:
                default += "/" + add
            else:
                break
    return path
