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
