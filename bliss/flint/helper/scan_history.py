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
    scan_type: str
    title: str


def get_all_scans(session_name: str) -> typing.List[ScanDesc]:
    """
    Returns all scans still references from the history.

    .. code-block:: python

        from bliss import current_session
        scans = get_scans(current_session.name)
        print(scans[0].node_name)
    """

    def read_safe_key(info, node_name, key, default):
        try:
            return info[key]
        except Exception:
            _logger.debug("Backtrace", exc_info=True)
            _logger.warning("%s from scan %s can't be read", key, node_name)
            return default

    session_node = get_session_node(session_name)
    scan_types = ("scan",)
    for scan in session_node.walk(
        wait=False, include_filter=scan_types, exclude_children=scan_types
    ):
        try:
            info = scan.info
            node_name = info["node_name"]
        except Exception:
            _logger.debug("Backtrace", exc_info=True)
            _logger.error("Error while reading a scan from the history")
        else:
            start_time = read_safe_key(info, node_name, "start_time", None)
            scan_nb = read_safe_key(info, node_name, "scan_nb", None)
            scan_type = read_safe_key(info, node_name, "type", None)
            title = read_safe_key(info, node_name, "title", "")
            yield ScanDesc(node_name, start_time, scan_nb, scan_type, title)


def get_scan_info(scan_node_name: str) -> typing.Dict:
    """Return a scan_info dict from the scan node_name"""
    scan = get_node(scan_node_name)
    return dict(scan.info.items())


def get_data_from_redis(
    scan_node_name: str, scan_info: typing.Dict
) -> typing.Dict[str, numpy.ndarray]:
    """Read channel data from redis, and referenced by this scan_info """
    channels = list(scan_info_helper.iter_channels(scan_info))
    channel_names = set([c.name for c in channels if c.info.get("dim", 0) == 0])

    result = {}
    scan = get_node(scan_node_name)
    for node in scan.walk(wait=False):
        if node.name not in channel_names:
            continue
        try:
            data = node.get_as_array(0, -1)
        except Exception:
            # It is supposed to fail if part of the measurements was dropped
            _logger.debug("Backtrace", exc_info=True)
            _logger.warning("Data from channel %s is not reachable", node.name)
        else:
            result[node.name] = data
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
    channel_names = set([c.name for c in channels if c.info.get("dim", 0) == 0])
    scan_nb = scan_info["scan_nb"]

    if "nexus" not in scan_info["data_writer"]:
        raise EnvironmentError("nexuswriter was not enabled for this scan")

    result = {}
    with h5py.File(scan_info["filename"], mode="r") as h5:
        devices = scan_info["nexuswriter"]["devices"]
        devices = device_info(devices, scan_info)
        for subscan_id, (_subscan, devices) in enumerate(devices.items(), 1):
            for channel_name, device in devices.items():
                if channel_name not in channel_names:
                    continue
                grpname = normalize_nexus_name(device["device_name"])
                dsetname = normalize_nexus_name(device["data_name"])
                path = f"/{scan_nb}.{subscan_id}/instrument/{grpname}/{dsetname}"
                try:
                    # Create a memory copy of the data
                    data = h5[path][()]
                except Exception:
                    _logger.debug("Backtrace", exc_info=True)
                    _logger.warning(
                        "Data from channel %s is not reachable", channel_name
                    )
                else:
                    result[channel_name] = data

    return result


def create_scan(scan_node_name: str) -> scan_model.Scan:
    """Create a scan with it's data from a Redis node_name.

    The scan could contain empty channels.
    """
    scan_info = get_scan_info(scan_node_name)
    scan = scan_info_helper.create_scan_model(scan_info)

    channels = list(scan_info_helper.iter_channels(scan_info))
    channel_names = set([c.name for c in channels if c.info.get("dim", 0) == 0])

    redis_data = get_data_from_redis(scan_node_name, scan_info)
    for channel_name, array in redis_data.items():
        data = scan_model.Data(parent=None, array=array)
        channel = scan.getChannelByName(channel_name)
        channel.setData(data)
        channel_names.discard(channel_name)

    if len(channel_names) > 0:
        try:
            hdf5_data = get_data_from_file(scan_node_name, scan_info)
        except Exception:
            _logger.debug("Error while reading data from HDF5", exc_info=True)
            _logger.error(
                "Impossible to read scan data '%s' from HDF5 files", scan_node_name
            )
        else:
            for channel_name, array in hdf5_data.items():
                if channel_name not in channel_names:
                    continue
                data = scan_model.Data(parent=None, array=array)
                channel = scan.getChannelByName(channel_name)
                channel.setData(data)
                channel_names.discard(channel_name)

    if len(channel_names) > 0:
        names = ", ".join(channel_names)
        _logger.error("Few channel data was not read '%s'", names)

    # I guess there is no way to reach the early scan_info
    scan._setFinalScanInfo(scan_info)
    scan._setState(scan_model.ScanState.FINISHED)
    return scan
