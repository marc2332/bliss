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
from ..model import plot_item_model


_logger = logging.getLogger(__name__)

Channel = collections.namedtuple("Channel", ["name", "kind", "device", "master"])


def _merge_master_keys(values: Dict, key: str):
    """
    Merge default and master keys in order to:
    - Provide masters first
    - Respect the order
    - Avoid duplication
    """
    result = list(values.get("master", {}).get(key, []))
    default = values.get(key, [])
    for k in default:
        if k not in result:
            result.append(k)
    return result


def iter_channels(scan_info: Dict[str, Any]):
    acquisition_chain = scan_info["acquisition_chain"]
    for master_name, data in acquisition_chain.items():
        scalars = _merge_master_keys(data, "scalars")
        spectra = _merge_master_keys(data, "spectra")
        images = _merge_master_keys(data, "images")

        for channel_name in scalars:
            device_name = channel_name.split(":")[0]
            channel = Channel(channel_name, "scalar", device_name, master_name)
            yield channel

        for channel_name in spectra:
            device_name = channel_name.split(":")[0]
            channel = Channel(channel_name, "spectrum", device_name, master_name)
            yield channel

        for channel_name in images:
            device_name = channel_name.split(":")[0]
            channel = Channel(channel_name, "image", device_name, master_name)
            yield channel


def create_scan_model(scan_info: Dict) -> scan_model.Scan:
    scan = scan_model.Scan()
    scan.setScanInfo(scan_info)

    devices: Dict[str, scan_model.Device] = {}
    channel_units = read_units(scan_info)
    channel_display_names = read_display_names(scan_info)

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
        unit = channel_units.get(channel_info.name, None)
        if unit is not None:
            channel.setUnit(unit)
        display_name = channel_display_names.get(channel_info.name, None)
        if display_name is not None:
            channel.setDisplayName(display_name)

    scan.seal()
    return scan


def read_units(scan_info: Dict) -> Dict[str, str]:
    """Merge all units together"""
    units = {}
    for _master, channel_dict in scan_info["acquisition_chain"].items():
        u = channel_dict.get("scalars_units", {})
        units.update(u)
        u = channel_dict.get("master", {}).get("scalars_units", {})
        units.update(u)
    return units


def read_display_names(scan_info: Dict) -> Dict[str, str]:
    """Merge all display names together"""
    display_names = {}
    for _master, channel_dict in scan_info["acquisition_chain"].items():
        u = channel_dict.get("display_names", {})
        display_names.update(u)
        u = channel_dict.get("master", {}).get("display_names", {})
        display_names.update(u)
    return display_names


def create_plot_model(scan_info: Dict) -> List[plot_model.Plot]:
    result: List[plot_model.Plot] = []

    channel_units = read_units(scan_info)

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
        plot = plot_item_model.CurvePlot()
        for master_name, channels_dict in scan_info["acquisition_chain"].items():
            scalars = channels_dict.get("scalars", [])
            master_channels = channels_dict.get("master", {}).get("scalars", [])

            if have_scatter:
                # In case of scatter the curve plot have to plot the time in x
                # Masters in y1 and the first value in y2

                for timer in scalars:
                    if timer in master_channels:
                        # skip the masters
                        continue
                    if channel_units.get(timer, None) != "s":
                        # skip non time base
                        continue
                    break
                else:
                    timer = None

                for scalar in scalars:
                    if scalar in master_channels:
                        # skip the masters
                        continue
                    if channel_units.get(scalar, None) == "s":
                        # skip the time base
                        continue
                    break
                else:
                    scalar = None

                if timer is not None:
                    if scalar is not None:
                        item = plot_item_model.CurveItem(plot)
                        x_channel = plot_model.ChannelRef(plot, timer)
                        y_channel = plot_model.ChannelRef(plot, scalar)
                        item.setXChannel(x_channel)
                        item.setYChannel(y_channel)
                        item.setYAxis("left")
                        plot.addItem(item)

                    for channel_name in master_channels:
                        item = plot_item_model.CurveItem(plot)
                        x_channel = plot_model.ChannelRef(plot, timer)
                        y_channel = plot_model.ChannelRef(plot, channel_name)
                        item.setXChannel(x_channel)
                        item.setYChannel(y_channel)
                        item.setYAxis("right")
                        plot.addItem(item)
                else:
                    # The plot will be empty
                    pass
            else:
                channels = [
                    m for m in master_channels if m.split(":")[0] == master_name
                ]
                if len(channels) > 0:
                    master_channel = channels[0]
                    master_channel_unit = channels_dict.get("master", {}).get(
                        "scalars_units", None
                    )
                    is_motor_scan = master_channel_unit != "s"
                else:
                    is_motor_scan = False

                for channel_name in scalars:
                    channel_unit = channels_dict.get("scalars_units", {}).get(
                        channel_name, None
                    )
                    if is_motor_scan and channel_unit == "s":
                        # Do not display base time for motor based scan
                        continue

                    item = plot_item_model.CurveItem(plot)
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
            if len(channels.get("master", {}).get("scalars", [])) < 2:
                # Not enough of a scatter
                continue

            plot = plot_item_model.ScatterPlot()
            scalars = channels.get("scalars", [])
            axes_channels = channels["master"]["scalars"]

            # Reach the first scalar which is not a time unit
            for scalar in scalars:
                if scalar in axes_channels:
                    # skip the masters
                    continue
                if channel_units.get(scalar, None) == "s":
                    # skip the time base
                    continue
                break
            else:
                scalar = None

            x_channel = plot_model.ChannelRef(plot, axes_channels[0])
            y_channel = plot_model.ChannelRef(plot, axes_channels[1])
            if scalar is not None:
                data_channel = plot_model.ChannelRef(plot, scalar)
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


def get_full_title(scan: scan_model.Scan) -> str:
    """Returns from scan_info a readable title"""
    scan_info = scan.scanInfo()
    if scan_info is None:
        return "No scan title"
    title = scan_info.get("title", "No scan title")
    scan_nb = scan_info.get("scan_nb", None)
    if scan_nb is None:
        text = f"{title} (#{scan_nb})"
    else:
        text = f"{title}"
    return text
