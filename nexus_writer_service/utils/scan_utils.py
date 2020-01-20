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
from .logging_utils import print_out


__all__ = ["open_data", "open_dataset"]


def scan_info(scan):
    """
    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns dict:
    """
    try:
        # bliss.scanning.scan.Scan -> dict
        return scan.scan_info
    except AttributeError:
        # bliss.data.nodes.scan.Scan -> dict
        return scan.info.get_all()


def is_scan_group(scan):
    """
    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns bool:
    """
    try:
        return scan.node.type == "scan_group"
    except AttributeError:
        return scan.type == "scan_group"


def scan_name(scan, subscan=1):
    """
    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns str:
    """
    info = scan_info(scan)
    return "{}.{}".format(info["scan_nb"], subscan)


def scan_filenames(scan, config=True):
    """
    Get filenames associated to a scan.

    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns list(str):
    """
    info = scan_info(scan)
    if config:
        try:
            return list(info["nexuswriter"]["filenames"])
        except KeyError:
            pass
    return [filename_int2ext(info["filename"])]


def session_filenames(scan_saving=None, config=True):
    """
    HDF5 file names to be saved by the external writer.
    """
    if config:
        return current_filenames(scan_saving=scan_saving)
    else:
        return [current_default_filename(scan_saving=scan_saving)]


def scan_uri(scan, subscan=1, config=True):
    """
    Get HDF5 uri associated to a scan.

    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :param int subscan:
    :param bool config: expect configurable writer
    :returns str:
    """
    filename = scan_filenames(scan, config=config)[0]
    if filename:
        return filename + "::/" + scan_name(scan, subscan=subscan)
    else:
        return ""


def scan_uris(scan, config=True):
    """
    Get HDF5 uri associated to a scan.

    :param list(bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan) scan:
    :param bool config: expect configurable writer
    :returns list(str):
    """
    try:
        tree = scan.acq_chain._tree
    except AttributeError:
        nsubscans = len(scan_info(scan)["acquisition_chain"])
    else:
        nsubscans = len(tree.children(tree.root))
    subscans = range(1, nsubscans + 1)
    return [scan_uri(scan, subscan=subscan, config=config) for subscan in subscans]


def current_internal_filename(scan_saving=None):
    """
    Filename for the internal writer.

    :returns str:
    """
    basename = config_utils.scan_saving_get(
        "data_filename", "", scan_saving=scan_saving
    )
    if basename:
        basename = os.path.splitext(basename)[0]
        return os.path.join(basename + ".h5")
    else:
        return ""


def filename_int2ext(filename=None, **overwrite):
    """
    Filename for the external writer, based on the filename for the internal writer.

    :param str filename:
    :param overwrite: overwrite template values
    :returns str:
    """
    if filename:
        return os.path.splitext(filename)[0] + "_external.h5"
    else:
        return "data_external.h5"


def current_directory(scan_saving=None, **overwrite):
    """
    Get path from the session's SCAN_SAVING object

    :param overwrite: overwrite template values
    :returns str:
    :raises RuntimeError: missing information
    """
    if scan_saving is None:
        scan_saving = config_utils.current_scan_saving()
    attrs = config_utils.scan_saving_attrs(
        template=scan_saving.template, scan_saving=scan_saving, **overwrite
    )
    try:
        return os.path.normpath(
            os.path.join(scan_saving.base_path, scan_saving.template.format(**attrs))
        )
    except KeyError as e:
        raise RuntimeError("Missing '{}' attribute in SCAN_SAVING".format(e))


def current_default_filename(scan_saving=None, **overwrite):
    """
    HDF5 file names to be saved by the external writer
    based on the filename of the internal writer.

    :param overwrite: overwrite template values
    :returns str:
    """
    filename = current_internal_filename(scan_saving=scan_saving, **overwrite)
    base_path = current_directory(scan_saving=scan_saving, **overwrite)
    return filename_int2ext(os.path.join(base_path, filename))


def current_filenames(scan_saving=None, **overwrite):
    """
    HDF5 file names to be saved by the external writer.
    The first is to write scan data and the other are
    masters to link scan entries.

    :param overwrite: overwrite template values
    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns list(str):
    """
    filenames = []
    name_templates = data_policy.filename_templates()
    base_path = current_directory(**overwrite)
    for name_template in name_templates:
        if name_template:
            attrs = config_utils.scan_saving_attrs(
                template=name_template, scan_saving=scan_saving, **overwrite
            )
            try:
                filename = name_template.format(**attrs)
            except KeyError:
                pass
            else:
                filename = os.path.join(base_path, filename)
                filenames.append(os.path.normpath(filename))
    if not filenames:
        filenames = [""]
    if not filenames[0]:
        # Data policy was not initialized
        filenames[0] = current_default_filename(scan_saving=scan_saving, **overwrite)
    return filenames


def open_uris(uris, block=False):
    """
    Open uri's in silx

    :param list(str): uris
    :param bool block: block thread until silx is closed
    """
    uris = [uri + "::/" if "::" not in uri else uri for uri in uris if uri]
    print_out("Opening {} ...".format(uris))
    if not uris:
        return
    p = gevent.subprocess.Popen(["silx", "view"] + uris)
    if block and p:
        p.wait()


def open_data(scan, block=False, subscan=1, config=True):
    """
    Open scan data in silx

    :param bool block: block thread until silx is closed
    :param int subscan:
    :param bool config: expect configurable writer
    """
    open_uris([scan_uri(scan, subscan=subscan, config=config)], block=block)


def open_dataset(scan, block=False, config=True):
    """
    Open dataset in silx

    :param bool block: block thread until silx is closed
    :param bool config: expect configurable writer
    """
    filename = scan_filenames(scan, config=config)[0]
    open_uris([filename], block=block)
