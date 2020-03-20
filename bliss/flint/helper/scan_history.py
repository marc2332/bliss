# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Helper to read scans from the history
"""

import logging
import typing
import numpy

from bliss.data.node import get_session_node
from bliss.data.node import get_node

from . import scan_info_helper
from bliss.flint.model import scan_model

_logger = logging.getLogger(__name__)


class ScanDesc(typing.NamedTuple):
    node_name: str
    start_time: object
    scan_nb: int
    title: str


def get_all_scans(session_name: str) -> typing.List[ScanDesc]:
    """
    Returns all scans still references from the history.

    .. code-block:: python
        from bliss import current_session
        scans = get_scans(current_session.name)
        print(scans[0].node_name)
    """
    session_node = get_session_node(session_name)
    for scan in session_node.iterator.walk(wait=False, filter="scan"):
        info = scan.info
        node_name = info["node_name"]
        start_time = info["start_time"]
        scan_nb = info["scan_nb"]
        title = info["title"]
        yield ScanDesc(node_name, start_time, scan_nb, title)


def get_scan_info(scan_node_name: str) -> typing.Dict:
    """Return a scan_info dict from the scan node_name"""
    scan = get_node(scan_node_name)
    return dict(scan.info.items())


def get_data_from_redis(
    scan_node_name: str, scan_info: typing.Dict
) -> typing.Dict[str, numpy.ndarray]:
    """Read channel data from redis, and referenced by this scan_info """
    channels = list(scan_info_helper.iter_channels(scan_info))
    channel_names = set([c.name for c in channels if c.kind == "scalar"])

    result = {}
    scan = get_node(scan_node_name)
    for node in scan.iterator.walk(wait=False):
        if node.name not in channel_names:
            continue
        try:
            data = node.get_as_array(0, -1)
            result[node.name] = data
        except:
            # It is supposed to fail if part of the measurements was dropped
            _logger.debug("Backtrace", exc_info=True)
            _logger.warning("Data from channel %s is not reachable", node.name)
    return result


def get_data_from_file(
    scan_node_name: str, scan_info
) -> typing.Dict[str, numpy.ndarray]:
    """Read channel data from HDF5, and referenced by this scan_info"""
    # Load it locally in case there is setup
    import h5py
    from nexus_writer_service.subscribers.devices import device_info
    from nexus_writer_service.subscribers.dataset_proxy import normalize_nexus_name

    channels = list(scan_info_helper.iter_channels(scan_info))
    channel_names = set([c.name for c in channels if c.kind == "scalar"])
    scan_nb = scan_info["scan_nb"]

    if "nexus" not in scan_info["data_writer"]:
        raise EnvironmentError("nexuswriter was not enabled for this scan")
    if "nexuswriter" not in scan_info:
        raise EnvironmentError("nexuswriter was not configured for this scan")
    if "filename" not in scan_info:
        raise EnvironmentError("no file was saved for this scan")

    result = {}
    with h5py.File(scan_info["filename"], mode="r") as h5:
        devices = scan_info["nexuswriter"]["devices"]
        devices = device_info(devices, scan_info)
        for subscan_id, (subscan, devices) in enumerate(devices.items()):
            subscan_id += 1
            for channel_name, device in devices.items():
                if channel_name not in channel_names:
                    continue
                grpname = normalize_nexus_name(device["device_name"])
                dsetname = normalize_nexus_name(device["data_name"])
                path = f"/{scan_nb}.{subscan_id}/instrument/{grpname}/{dsetname}"
                try:
                    data = h5[path][...]
                    result[channel_name] = data
                except:
                    # It is supposed to fail if part of the measurements was dropped
                    _logger.debug("Backtrace", exc_info=True)
                    _logger.warning(
                        "Data from channel %s is not reachable", channel_name
                    )

    return result


def create_scan(scan_node_name: str) -> scan_model.Scan:
    """Create a scan with it's data from a Redis node_name.

    The scan could contain empty channels.
    """
    scan_info = get_scan_info(scan_node_name)
    scan = scan_info_helper.create_scan_model(scan_info)

    redis_data = get_data_from_redis(scan_node_name, scan_info)
    for channel_name, array in redis_data.items():
        data = scan_model.Data(parent=None, array=array)
        channel = scan.getChannelByName(channel_name)
        channel.setData(data)
    return scan
