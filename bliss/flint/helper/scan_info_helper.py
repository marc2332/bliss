# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides a storage for raw data coming from live scans.
"""
from __future__ import annotations
from typing import Any
from typing import Dict

import collections
import logging
from ..model import scan_model


_logger = logging.getLogger(__name__)

Channel = collections.namedtuple("Channel", ["name", "kind", "device", "master"])


def iter_channels(scan_info: Dict[str, Any]):
    acquisition_chain = scan_info["acquisition_chain"]
    for master_name, data in acquisition_chain.items():
        scalars = data.get("scalars", [])
        spectra = data.get("spectra", [])
        images = data.get("images", [])
        if "master" in data:
            master_data = data["master"]
            scalars.extend(master_data.get("scalars", []))
            spectra.extend(master_data.get("spectra", []))
            images.extend(master_data.get("images", []))

        scalars = list(set(scalars))
        for channel_name in scalars:
            device_name = channel_name.split(":")[0]
            channel = Channel(channel_name, "scalar", device_name, master_name)
            yield channel

        spectra = list(set(spectra))
        for channel_name in spectra:
            device_name = channel_name.split(":")[0]
            channel = Channel(channel_name, "spectrum", device_name, master_name)
            yield channel

        images = list(set(images))
        for channel_name in images:
            device_name = channel_name.split(":")[0]
            channel = Channel(channel_name, "image", device_name, master_name)
            yield channel


def create_scan_model(scan_info: Dict) -> scan_model.Scan:
    scan = scan_model.Scan()

    devices: Dict[str, scan_model.Device] = {}

    # Mapping from scan_info to scan model
    kinds = {
        "scalar": scan_model.ChannelType.COUNTER,
        "spectrum": scan_model.ChannelType.SPECTRUM,
        "image": scan_model.ChannelType.IMAGE,
    }

    channels = iter_channels(scan_info)
    for channel_info in channels:
        if channel_info.device in devices:
            device = devices[channel_info.device]
        else:
            # Device have to be created
            if channel_info.master == channel_info.device:
                device = scan_model.Device(scan)
                device.setName(channel_info.device)
                devices[channel_info.device] = device
            else:
                if channel_info.master in devices:
                    master = devices[channel_info.master]
                else:
                    # Master have to be created
                    master = scan_model.Device(scan)
                    master.setName(channel_info.master)
                    devices[channel_info.master] = master
                device = scan_model.Device(scan)
                device.setName(channel_info.device)
                device.setMaster(master)
                devices[channel_info.device] = device

        kind = kinds.get(channel_info.kind, None)
        if kind is None:
            _logger.error(
                "Channel kind '%s' unknown. Channel %s skipped.",
                channel_info.kind,
                channel_info.name,
            )
            continue

        channel = scan_model.Channel(device)
        channel.setName(channel_info.name)
        channel.setType(kind)

    scan.seal()
    return scan
