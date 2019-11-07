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

import os
import gevent
from . import config_utils
from . import data_policy


__all__ = ["open_dataset"]


def scan_name(info, subscan=1):
    """
    :param bliss.scanning.scan.Scan or dict scan_info:
    :returns str:
    """
    if not isinstance(info, dict):
        info = info.scan_info
    return "{}.{}".format(info["scan_nb"], subscan)


def internal_filename():
    """
    Filename of internal writer

    :returns str:
    """
    base_path = directory()
    basename = config_utils.scan_saving_get("data_filename", "")
    if basename == "<no saving>":
        basename = ""
    if basename:
        return os.path.join(base_path, basename + ".h5")
    else:
        return ""


def scan_filename_int2ext(filename=None):
    """
    :param str filename:
    :returns str:
    """
    dirname = os.path.dirname(filename)
    basename = os.path.basename(filename)
    if basename and basename != "<no saving>":
        basename = os.path.splitext(basename)[0] + "_external.h5"
    else:
        basename = "data_external.h5"
    return os.path.join(dirname, basename)


def directory(**replace):
    """
    Get path from the session's SCAN_SAVING object

    :returns str:
    :raises RuntimeError: missing information
    """
    scan_saving = config_utils.scan_saving()
    attrs = config_utils.scan_saving_attrs(scan_saving.template)
    for k, v in replace.items():
        attrs[k] = v
    try:
        return os.path.normpath(
            os.path.join(scan_saving.base_path, scan_saving.template.format(**attrs))
        )
    except KeyError as e:
        raise RuntimeError("Missing '{}' attribute in SCAN_SAVING".format(e))


def filenames(**replace):
    """
    HDF5 file names to be save by the external writer.
    The first is to write scan data and the other are
    masters to link scan entries.

    :returns list(str):
    """
    relpath = "."
    filenames = []
    name_templates = data_policy.filename_templates()
    base_path = directory(**replace)
    for name_template in name_templates:
        if name_template:
            attrs = config_utils.scan_saving_attrs(name_template)
            try:
                filename = name_template.format(**attrs)
            except KeyError:
                pass
            else:
                filename = os.path.join(base_path, relpath, filename)
                filenames.append(os.path.normpath(filename))
        relpath = os.path.join("..", relpath)
    if not filenames:
        filenames = [""]
    if not filenames[0]:
        # Data policy was not initialized
        filename = internal_filename()
        filename = scan_filename_int2ext(filename)
        filenames[0] = os.path.join(base_path, filename)
    return filenames


def dataset_files():
    """
    All HDF5 file names of the current dataset

    :returns list(str):
    """
    lst = filenames()
    internal = internal_filename()
    if internal and internal not in lst:
        lst.append(internal)
    return lst


def open_dataset(block=False):
    """
    Open current dataset in silx

    :param bool block: block repl
    """
    uris = [uri + "::/" if "::" not in uri else uri for uri in dataset_files()]
    print("Opening {} ...".format(uris))
    p = gevent.subprocess.Popen(["silx", "view"] + uris)
    if block:
        p.wait()
    else:
        return p
