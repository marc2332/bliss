# -*- coding: utf-8 -*-
#
# This obj is part of the nexus writer service of the BLISS project.
#
# Code is maintained by the ESRF Data Analysis Unit.
#
# Original author: Wout de Nolf
#
# Copyright (c) 2015-2019 ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import h5py
import traceback
from . import monkey
from ..utils.logging_utils import print_err


OPEN_OBJECTS = {}


def _store(obj):
    oid = obj.id
    if oid not in OPEN_OBJECTS:
        stack = traceback.extract_stack()
        stack.pop()
        stack.pop()
        OPEN_OBJECTS[oid] = stack


def _purge():
    for oid in list(OPEN_OBJECTS.keys()):
        if not oid.valid:
            OPEN_OBJECTS.pop(oid)


def _tracking_file(old_class):
    class trackingFile(old_class):
        def __init__(self, *args, **kwargs):
            super(trackingFile, self).__init__(*args, **kwargs)
            _store(self)
            self._keepname = name = uri_from_id(self.id)
            print_open_objects(" AFTER OPENING FILE " + repr(name))

        def close(self, *args, **kwargs):
            super(trackingFile, self).close(*args, **kwargs)
            _purge()
            print_open_objects(" AFTER CLOSING FILE " + repr(self._keepname))

    return trackingFile


def _tracking_group(old_class):
    class trackingGroup(old_class):
        def __init__(self, *args, **kwargs):
            super(trackingGroup, self).__init__(*args, **kwargs)
            _store(self)
            uri = uri_from_id(self.id)
            print_open_objects(" AFTER OPENING GROUP " + repr(uri))

    return trackingGroup


def _tracking_dataset(old_class):
    class trackingDataset(old_class):
        def __init__(self, *args, **kwargs):
            super(trackingDataset, self).__init__(*args, **kwargs)
            _store(self)
            uri = uri_from_id(self.id)
            print_open_objects(" AFTER OPENING DATASET " + repr(uri))

    return trackingDataset


def uri_from_id(oid):
    uri = h5py.h5i.get_name(oid)
    if uri:
        uri = uri.decode()
    else:
        uri = str(oid)
    filename = h5py.h5f.get_name(oid)
    if filename:
        uri = filename.decode() + "::" + uri
    return uri


def type_from_id(oid):
    if isinstance(oid, h5py.h5f.FileID):
        return "file"
    elif isinstance(oid, h5py.h5g.GroupID):
        return "group"
    elif isinstance(oid, h5py.h5d.DatasetID):
        return "dataset"
    else:
        return "object"


def print_open_objects(msg="", **kwargs):
    print_err("\n### {} OPEN HDF5 OBJECTS{}".format(len(OPEN_OBJECTS), msg), **kwargs)
    sep = ""
    for oid, stack in OPEN_OBJECTS.items():
        if not oid.valid:
            continue
        stack = sep.join(traceback.format_list(stack))
        name = repr(uri_from_id(oid))
        otype = type_from_id(oid)
        print_err("\n Open {} {}\n{}{}".format(otype, name, sep, stack), **kwargs)
    print_err("\n### END OPEN HDF5 OBJECTS\n", **kwargs)


def patch(file=True, group=False, dataset=False):
    if file:
        for mod in [h5py, h5py._hl.files]:
            newitem = _tracking_file(monkey.original(mod, "File"))
            monkey.patch_item(mod, "File", newitem)
    if group:
        for mod in [h5py, h5py._hl.group]:
            newitem = _tracking_group(monkey.original(mod, "Group"))
            monkey.patch_item(mod, "Group", newitem)
    if dataset:
        for mod in [h5py, h5py._hl.dataset]:
            newitem = _tracking_dataset(monkey.original(mod, "Dataset"))
            monkey.patch_item(mod, "Dataset", newitem)


def unpatch():
    monkey.unpatch_item(h5py, "File")
    monkey.unpatch_item(h5py, "Group")
    monkey.unpatch_item(h5py, "Dataset")
    monkey.unpatch_item(h5py._hl.files, "File")
    monkey.unpatch_item(h5py._hl.group, "Group")
    monkey.unpatch_item(h5py._hl.dataset, "Dataset")
