# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""
Provides helper to read scan_info.
"""
from __future__ import annotations
from typing import Any
from typing import Dict
from typing import List

import collections
import logging
from ..model import scan_model
from ..model import plot_model
from ..model import plot_curve_model
from ..model import plot_item_model


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


def create_plot_model(scan_info: Dict) -> List[plot_model.Plot]:

    result: List[plot_model.Plot] = []

    have_scalar = False
    have_scatter = False
    for _master, channels in scan_info["acquisition_chain"].items():
        scalars = channels.get("scalars", [])
        if len(scalars) > 0:
            have_scalar = True
        if (
            len(channels.get("master", {}).get("scalars", [])) >= 2
            and scan_info.get("data_dim", 1) == 2
        ):
            have_scatter = True

    # Scalar plot

    if have_scalar:
        plot = plot_curve_model.CurvePlot()
        for _master, channels in scan_info["acquisition_chain"].items():
            scalars = channels.get("scalars", [])
            master_channels = channels.get("master", {}).get("scalars", [])

            for channel_name in scalars:
                item = plot_curve_model.CurveItem(plot)
                data_channel = plot_model.ChannelRef(plot, channel_name)

                if len(master_channels) == 0:
                    master_channel = None
                else:
                    master_channel = plot_model.ChannelRef(plot, master_channels[0])

                item.setXChannel(master_channel)
                item.setYChannel(data_channel)
                plot.addItem(item)

        result.append(plot)

    # Scatter plot

    if have_scatter:
        for _master, channels in scan_info["acquisition_chain"].items():
            plot = plot_item_model.ScatterPlot()

            scalars = channels.get("scalars", [])
            axes_channels = channels["master"]["scalars"]
            assert len(axes_channels) >= 2

            x_channel = plot_model.ChannelRef(plot, axes_channels[0])
            y_channel = plot_model.ChannelRef(plot, axes_channels[1])
            if len(scalars) > 0:
                data_channel = plot_model.ChannelRef(plot, scalars[0])
            else:
                data_channel = None

            item = plot_item_model.ScatterItem(plot)
            item.setXChannel(x_channel)
            item.setYChannel(y_channel)
            item.setValueChannel(data_channel)
            # FIXME: Have to do something with: scan_info.get("title", ""),
            # FIXME: Have to do something with: scan_info.get("instrument", {}).get("positioners", dict()),
            plot.addItem(item)

            result.append(plot)

    # MCA plot

    for _master, channels in scan_info["acquisition_chain"].items():
        spectra = channels.get("spectra", [])
        # merge master which are spectra
        if "spectra" in channels:
            for c in channels.get("master", {}).get("spectra", []):
                if c not in spectra:
                    spectra.append(c)

        for spectrum_name in spectra:
            plot = plot_item_model.McaPlot()
            mca_channel = plot_model.ChannelRef(plot, spectrum_name)
            item = plot_item_model.McaItem(plot)
            item.setMcaChannel(mca_channel)
            plot.addItem(item)
            result.append(plot)

    # Image plot

    for _master, channels in scan_info["acquisition_chain"].items():
        images = channels.get("images", [])
        # merge master which are image
        if "master" in channels:
            for c in channels.get("master", {}).get("images", []):
                if c not in images:
                    images.append(c)

        for image_name in images:
            plot = plot_item_model.ImagePlot()
            image_channel = plot_model.ChannelRef(plot, image_name)
            item = plot_item_model.ImageItem(plot)
            item.setImageChannel(image_channel)
            plot.addItem(item)
            result.append(plot)

    return result
