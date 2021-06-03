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

import os
import gevent
from . import session_utils
from . import data_policy
from .logging_utils import print_out


__all__ = ["open_data", "open_dataset", "open_dataset_collection", "open_proposal"]


def scan_info(scan):
    """
    :param Scan or ScanNode scan:
    :returns dict:
    """
    try:
        # Scan
        return scan.scan_info
    except AttributeError:
        # ScanNode
        return scan.info.get_all()


def scan_info_get(scan, key, default=None):
    """
    :param Scan or ScanNode scan:
    :param str key:
    :param default:
    """
    try:
        # Scan
        return scan.scan_info.get(key, default)
    except AttributeError:
        # ScanNode
        return scan.info.get(key, default)


def scan_node(scan):
    """
    :param Scan or ScanNode scan:
    :returns ScanNode:
    """
    try:
        # Scan
        return scan.node
    except AttributeError:
        # ScanNode
        return scan


def is_scan_group(scan):
    """
    :param Scan or ScanNode scan:
    :returns bool:
    """
    try:
        return scan.node.type == "scan_group"
    except AttributeError:
        return scan.type == "scan_group"


def scan_name(scan, subscan=1):
    """
    :param Scan or ScanNode scan:
    :returns str:
    """
    data_writer = scan_info_get(scan, "data_writer")
    if data_writer == "nexus":
        scan_nb = scan_info_get(scan, "scan_nb")
        return f"{scan_nb}.{subscan}"
    else:
        name = scan_node(scan).name
        if subscan == 1:
            return name
        else:
            scan_number, scan_name = name.split("_", maxsplit=1)
            return f"{scan_number}{'.%d_' % subscan-1}{scan_name}"


def scan_filename(scan):
    """
    Name of the file that contains the scan data

    :param Scan or ScanNode scan:
    :returns str or None:
    """
    return scan_info_get(scan, "filename")


@session_utils.with_scan_saving
def session_filename(scan_saving=None):
    """
    Name of the file that contains the scan data of the current BLISS session

    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns str or None:
    """
    return session_utils.scan_saving_get(
        "filename", default=None, scan_saving=scan_saving
    )


def scan_master_filenames(scan, config=True):
    """
    Names of the files that contain links to the scan data

    :param Scan or ScanNode scan:
    :param bool config: configurable writer is used
    :returns dict(str):
    """
    if not config:
        return {}
    info = scan_info_get(scan, "nexuswriter", {})
    return info.get("masterfiles", {})


@session_utils.with_scan_saving
def session_master_filenames(scan_saving=None, config=True):
    """
    Names of the files that contain links to the scan data of the current BLISS session

    :param bliss.scanning.scan.ScanSaving scan_saving:
    :param bool config: configurable writer is used
    :returns dict(str):
    """
    if scan_saving.data_policy != "ESRF" or not config or scan_saving.writer != "nexus":
        return {}
    eval_dict = {}
    root_path = scan_saving.get_cached_property("root_path", eval_dict=eval_dict)
    relative_templates = data_policy.masterfile_templates()
    return {
        name: scan_saving.eval_template(
            os.path.abspath(os.path.join(root_path, s)), eval_dict=eval_dict
        )
        for name, s in relative_templates.items()
    }


def scan_filenames(scan, config=True):
    """
    Names of the files that contain the scan data (raw or as links)

    :param Scan or ScanNode scan:
    :pram bool config: writer parses the extra "nexuswriter" info
    :returns dict(str):
    """
    filenames = {}
    filename = scan_info_get(scan, "filename", None)
    if filename:
        filenames["dataset"] = filename
    if config:
        info = scan_info_get(scan, "nexuswriter", {})
        filenames.update(info.get("masterfiles", {}))
    return filenames


@session_utils.with_scan_saving
def session_filenames(scan_saving=None, config=True):
    """
    Names of the files that contain links to the scan data (raw or as links) of the current BLISS session

    :param bliss.scanning.scan.ScanSaving scan_saving:
    :pram bool config: writer parses the extra "nexuswriter" info
    :returns list(str):
    """
    filenames = {}
    filename = session_filename(scan_saving=scan_saving)
    if filename:
        filenames["dataset"] = filename
    if config:
        filenames.update(
            session_master_filenames(scan_saving=scan_saving, config=config)
        )
    return filenames


def scan_uri(scan, subscan=1):
    """
    Get HDF5 uri associated to a scan.

    :param Scan or ScanNode scan:
    :param int subscan:
    :returns str or None:
    """
    filename = scan_filename(scan)
    if filename:
        return filename + "::/" + scan_name(scan, subscan=subscan)
    else:
        return filename


def scan_uris(scan, subscan=None):
    """
    Get all scan data uri's, one for each subscan.

    :param list(Scan or ScanNode) scan:
    :param int subscan: all subscans by default
    :returns list(str):
    """
    if subscan is None:
        try:
            tree = scan.acq_chain._tree
        except AttributeError:
            nsubscans = len(scan_info_get(scan, "acquisition_chain", []))
        else:
            nsubscans = len(tree.children(tree.root))
        subscans = range(1, nsubscans + 1)
    else:
        subscans = [subscan]
    return list(filter(None, [scan_uri(scan, subscan=subscan) for subscan in subscans]))


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


def open_data(scan, subscan=None, block=False):
    """
    Open scan data in silx

    :param int subscan:
    :param bool block: block thread until silx is closed
    """
    uris = scan_uris(scan, subscan=subscan)
    open_uris(uris, block=block)


def open_dataset(scan, block=False):
    """
    Open dataset in silx

    :param bool block: block thread until silx is closed
    """
    filename = scan_filename(scan)
    if filename:
        open_uris([filename], block=block)
    else:
        print_out("No data saved for this scan")


def open_dataset_collection(scan, block=False, config=True):
    """
    Open collection in silx

    :param bool block: block thread until silx is closed
    :param bool config: configurable writer is used
    """
    filename = scan_master_filenames(scan, config=config).get("dataset_collection")
    if filename:
        open_uris([filename], block=block)
    else:
        print_out("No master links for this scan")


def open_proposal(scan, block=False, config=True):
    """
    Open proposal in silx

    :param bool block: block thread until silx is closed
    :param bool config: configurable writer is used
    """
    filename = scan_master_filenames(scan, config=config).get("proposal")
    if filename:
        open_uris([filename], block=block)
    else:
        print_out("No master links for this scan")
