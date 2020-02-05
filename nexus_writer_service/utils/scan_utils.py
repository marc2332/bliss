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
from . import config_utils
from . import data_policy
from .logging_utils import print_out


__all__ = ["open_data", "open_dataset", "open_sample", "open_proposal"]


def scan_info(scan):
    """
    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns dict:
    """
    try:
        # bliss.scanning.scan.Scan
        return scan.scan_info
    except AttributeError:
        # bliss.data.nodes.scan.Scan
        return scan.info.get_all()


def scan_node(scan):
    """
    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns bliss.data.nodes.scan.Scan:
    """
    try:
        # bliss.scanning.scan.Scan
        return scan.node
    except AttributeError:
        # bliss.data.nodes.scan.Scan
        return scan


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
    if info["data_writer"] == "nexus":
        return "{}.{}".format(info["scan_nb"], subscan)
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

    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :returns str or None:
    """
    return scan_info(scan).get("filename", None)


@config_utils.with_scan_saving
def session_filename(scan_saving=None):
    """
    Name of the file that contains the scan data of the current BLISS session

    :param bliss.scanning.scan.ScanSaving scan_saving:
    :returns str or None:
    """
    return config_utils.scan_saving_get(
        "filename", default=None, scan_saving=scan_saving
    )


def scan_master_filenames(scan, config=True):
    """
    Names of the files that contain links to the scan data

    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :param bool config: configurable writer is used
    :returns dict(str):
    """
    if not config:
        return {}
    info = scan_info(scan)
    return info.get("nexuswriter", {}).get("masterfiles", {})


@config_utils.with_scan_saving
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

    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
    :pram bool config: writer parses the extra "nexuswriter" info
    :returns dict(str):
    """
    filenames = {}
    info = scan_info(scan)
    filename = info.get("filename", None)
    if filename:
        filenames["dataset"] = filename
    if config:
        filenames.update(info.get("nexuswriter", {}).get("masterfiles", {}))
    return filenames


@config_utils.with_scan_saving
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

    :param bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan scan:
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

    :param list(bliss.scanning.scan.Scan or bliss.data.nodes.scan.Scan) scan:
    :param int subscan: all subscans by default
    :returns list(str):
    """
    if subscan is None:
        try:
            tree = scan.acq_chain._tree
        except AttributeError:
            nsubscans = len(scan_info(scan)["acquisition_chain"])
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


def open_sample(scan, block=False, config=True):
    """
    Open sample in silx

    :param bool block: block thread until silx is closed
    :param bool config: configurable writer is used
    """
    filename = scan_master_filenames(scan, config=config).get("sample")
    if filename:
        open_uris([filename], block=block)
    else:
        print_out("No master links for this scan")


def open_proposal(scan, block=False, config=True):
    """
    Open sample in silx

    :param bool block: block thread until silx is closed
    :param bool config: configurable writer is used
    """
    filename = scan_master_filenames(scan, config=config).get("proposal")
    if filename:
        open_uris([filename], block=block)
    else:
        print_out("No master links for this scan")
