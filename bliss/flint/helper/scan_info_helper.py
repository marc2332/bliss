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
from typing import Optional
from typing import MutableMapping

import weakref
import collections
import logging
from ..model import scan_model
from ..model import plot_model
from ..model import plot_item_model
from . import model_helper


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

    def get_device_from_channel_name(channel_name):
        """Returns the device name from the channel name, else None"""
        if ":" in channel_name:
            elements = channel_name.split(":")
            return ":".join(elements[0:-1])
        return None

    for master_name, data in acquisition_chain.items():
        scalars = _merge_master_keys(data, "scalars")
        spectra = _merge_master_keys(data, "spectra")
        images = _merge_master_keys(data, "images")

        for channel_name in scalars:
            device_name = get_device_from_channel_name(channel_name)
            channel = Channel(channel_name, "scalar", device_name, master_name)
            yield channel

        for channel_name in spectra:
            device_name = get_device_from_channel_name(channel_name)
            channel = Channel(channel_name, "spectrum", device_name, master_name)
            yield channel

        for channel_name in images:
            device_name = get_device_from_channel_name(channel_name)
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

    channelsDict = {}
    channels = iter_channels(scan_info)
    for channel_info in channels:
        device_name = channel_info.device

        key = channel_info.master
        master = devices.get(key, None)
        if master is None:
            # Master have to be created
            master = scan_model.Device(scan)
            master.setName(channel_info.master)
            devices[key] = master

        device = None
        if channel_info.device is not None:
            key = channel_info.master + ":" + channel_info.device
            device = devices.get(key, None)
            if device is None:
                device = scan_model.Device(scan)
                device.setName(device_name)
                device.setMaster(master)
                devices[key] = device
        else:
            device = master

        kind = kinds.get(channel_info.kind, None)
        if kind is None:
            _logger.error(
                "Channel kind '%s' unknown. Channel %s skipped.",
                channel_info.kind,
                channel_info.name,
            )
            continue

        channel = scan_model.Channel(device)
        channelsDict[channel_info.name] = channel
        channel.setName(channel_info.name)
        channel.setType(kind)
        unit = channel_units.get(channel_info.name, None)
        if unit is not None:
            channel.setUnit(unit)
        display_name = channel_display_names.get(channel_info.name, None)
        if display_name is not None:
            channel.setDisplayName(display_name)

    requests = scan_info.get("requests", None)
    if requests:
        for channel_name, metadata_dict in requests.items():
            channel = channelsDict.get(channel_name, None)
            if channel is not None:
                metadata = parse_channel_metadata(metadata_dict)
                channel.setMetadata(metadata)
            else:
                _logger.warning(
                    "Channel %s is part of the request but not part of the acquisition chain. Info ingored",
                    channel_name,
                )

    scan.seal()
    return scan


def read_units(scan_info: Dict) -> Dict[str, str]:
    """Merge all units together"""
    units: Dict[str, str] = {}
    for _master, channel_dict in scan_info["acquisition_chain"].items():
        u = channel_dict.get("scalars_units", {})
        units.update(u)
        u = channel_dict.get("master", {}).get("scalars_units", {})
        units.update(u)
    return units


def read_display_names(scan_info: Dict) -> Dict[str, str]:
    """Merge all display names together"""
    display_names: Dict[str, str] = {}
    for _master, channel_dict in scan_info["acquisition_chain"].items():
        u = channel_dict.get("display_names", {})
        display_names.update(u)
        u = channel_dict.get("master", {}).get("display_names", {})
        display_names.update(u)
    return display_names


def _pop_and_convert(meta, key, func):
    value = meta.pop(key, None)
    if value is None:
        return None
    try:
        value = func(value)
    except ValueError:
        _logger.warning("%s %s is not a valid value. Field ignored.", key, value)
        value = None
    return value


def parse_channel_metadata(meta: Dict) -> scan_model.ChannelMetadata:
    meta = meta.copy()

    # Compatibility Bliss 1.0
    if "axes-points" in meta and "axis-points" not in meta:
        _logger.warning("Metadata axes-points have to be replaced by axis-points.")
        meta["axis-points"] = meta.pop("axes-points")
    if "axes-kind" in meta and "axis-kind" not in meta:
        _logger.warning("Metadata axes-kind have to be replaced by axis-kind.")
        meta["axis-kind"] = meta.pop("axes-kind")

    start = _pop_and_convert(meta, "start", float)
    stop = _pop_and_convert(meta, "stop", float)
    vmin = _pop_and_convert(meta, "min", float)
    vmax = _pop_and_convert(meta, "max", float)
    points = _pop_and_convert(meta, "points", int)
    axisPoints = _pop_and_convert(meta, "axis-points", int)
    axisKind = _pop_and_convert(meta, "axis-kind", scan_model.AxisKind)

    for key in meta.keys():
        _logger.warning("Metadata key %s is unknown. Field ignored.", key)

    return scan_model.ChannelMetadata(
        start, stop, vmin, vmax, points, axisPoints, axisKind
    )


def create_plot_model(
    scan_info: Dict, scan: Optional[scan_model.Scan] = None
) -> List[plot_model.Plot]:
    result: List[plot_model.Plot] = []

    channel_units = read_units(scan_info)

    default_plot = None

    have_scalar = False
    have_scatter = False
    for _master, channels in scan_info["acquisition_chain"].items():
        scalars = channels.get("scalars", [])
        if len(scalars) > 0:
            have_scalar = True
        if scan_info.get("data_dim", 1) == 2 or scan_info.get("dim", 1) == 2:
            have_scatter = True

    # Scalar plot

    if have_scalar:
        plot = plot_item_model.CurvePlot()
        if not have_scalar:
            default_plot = plot

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
            plot = plot_item_model.ScatterPlot()
            if default_plot is None:
                default_plot = plot

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

            if len(axes_channels) >= 1:
                x_channel = plot_model.ChannelRef(plot, axes_channels[0])
            else:
                x_channel = None

            if len(axes_channels) >= 2:
                y_channel = plot_model.ChannelRef(plot, axes_channels[1])
            else:
                y_channel = None

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
        spectra: List[str] = []
        spectra += channels.get("spectra", [])
        # merge master which are spectra
        if "spectra" in channels:
            for c in channels.get("master", {}).get("spectra", []):
                if c not in spectra:
                    spectra.append(c)

        for spectrum_name in spectra:
            plot = plot_item_model.McaPlot()
            if default_plot is None:
                default_plot = plot
            mca_channel = plot_model.ChannelRef(plot, spectrum_name)
            item = plot_item_model.McaItem(plot)
            item.setMcaChannel(mca_channel)
            plot.addItem(item)
            result.append(plot)

    # Image plot

    for _master, channels in scan_info["acquisition_chain"].items():
        images: List[str] = []
        images += channels.get("images", [])
        # merge master which are image
        if "master" in channels:
            for c in channels.get("master", {}).get("images", []):
                if c not in images:
                    images.append(c)

        for image_name in images:
            plot = plot_item_model.ImagePlot()
            if default_plot is None:
                default_plot = plot
            image_channel = plot_model.ChannelRef(plot, image_name)
            item = plot_item_model.ImageItem(plot)
            item.setImageChannel(image_channel)
            plot.addItem(item)
            result.append(plot)

    if default_plot is not None:
        # Move the default plot on to
        result.remove(default_plot)
        result.insert(0, default_plot)

    display_extra = scan_info.get("_display_extra", None)
    if display_extra is not None:
        if scan is None:
            scan = create_scan_model(scan_info)
        displayed_channels = display_extra.get("displayed_channels", None)
        # Sanitize
        if displayed_channels is not None:
            if not isinstance(displayed_channels, list):
                _logger.warning(
                    "_display_extra.displayed_channels is not a list: Key ignored"
                )
                displayed_channels = None
            elif len([False for i in displayed_channels if not isinstance(i, str)]) > 0:
                _logger.warning(
                    "_display_extra.displayed_channels must only contains strings: Key ignored"
                )
                displayed_channels = None

        if displayed_channels is not None:
            for plot in result:
                if isinstance(
                    plot, (plot_item_model.CurvePlot, plot_item_model.ScatterPlot)
                ):
                    model_helper.updateDisplayedChannelNames(
                        plot, scan, displayed_channels
                    )

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


_PROGRESS_STRATEGIES: MutableMapping[
    scan_model.Scan, List[_ProgressStrategy]
] = weakref.WeakKeyDictionary()


class _ProgressStrategy:
    def compute(self, scan: scan_model.Scan) -> Optional[float]:
        """Returns the percent of progress of this strategy.

        Returns a value between 0..1, else None if it is not appliable.
        """
        raise NotImplementedError

    def channelSize(self, channel: scan_model.Channel):
        data = channel.data()
        if data is None:
            return 0.0

        if data.frameId() is not None:
            size = data.frameId() + 1
        else:
            size = len(data.array())

        return size


class _ProgressOfAnyChannels(_ProgressStrategy):
    """Compute the progress according to any of the available channels"""

    def __init__(self, maxPoints: int):
        self.__maxPoints = maxPoints

    def compute(self, scan: scan_model.Scan) -> Optional[float]:
        scan_info = scan.scanInfo()
        master_channels: List[str] = []
        for _master_name, channel_info in scan_info["acquisition_chain"].items():
            master_channels.extend(channel_info.get("master", {}).get("scalars", []))
            master_channels.extend(channel_info.get("master", {}).get("images", []))

        for master_channel in master_channels:
            channel = scan.getChannelByName(master_channel)
            if channel is None:
                continue
            size = self.channelSize(channel)
            return size / self.__maxPoints

        return None


class _ProgressOfChannel(_ProgressStrategy):
    def __init__(self, channelName: str, maxPoints: int):
        self.__maxPoints = maxPoints
        self.__channelName = channelName

    def compute(self, scan: scan_model.Scan) -> Optional[float]:
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        size = self.channelSize(channel)
        return size / self.__maxPoints


def _create_progress_strategies(scan: scan_model.Scan) -> List[_ProgressStrategy]:
    scan_info = scan.scanInfo()
    if scan_info is None:
        return []

    strategies = []

    requests = scan_info.get("requests", None)
    if requests:
        # Reach on channel per npoints (in case of many top masters without
        # same size)
        strategy_per_npoints: Dict[int, _ProgressStrategy] = {}
        for channel_name, metadata_dict in requests.items():
            if "points" in metadata_dict:
                try:
                    npoints = int(metadata_dict["points"])
                except Exception:
                    # It's about parsing user input, everything can happen
                    _logger.error("Error while reading scan_info", exc_info=True)
                    continue

                if npoints in strategy_per_npoints:
                    continue
                strategy = _ProgressOfChannel(channel_name, npoints)
                strategy_per_npoints[npoints] = strategy

        for _, s in strategy_per_npoints.items():
            strategies.append(s)

    if len(strategies) == 0:
        # npoints do not distinguish many top masters
        # It only use it if there is no other choises
        try:
            npoints = scan_info.get("npoints", None)
            if npoints is None:
                # Mesh scans
                npoints1 = scan_info.get("npoints1", 0)
                npoints2 = scan_info.get("npoints2", 0)
                npoints = int(npoints1) * int(npoints2)
            else:
                npoints = int(npoints)

            if npoints is not None and npoints != 0:
                strategies.append(_ProgressOfAnyChannels(npoints))
        except Exception:
            # It's about parsing user input, everything can happen
            _logger.error("Error while reading scan_info", exc_info=True)

    return strategies


def get_scan_progress_percent(scan: scan_model.Scan) -> Optional[float]:
    """Returns the percent of progress of this strategy.

    Returns a value between 0..1, else None if it is not appliable.
    """
    strategies = _PROGRESS_STRATEGIES.get(scan, None)
    if strategies is None:
        strategies = _create_progress_strategies(scan)
        _PROGRESS_STRATEGIES[scan] = strategies

    values = [s.compute(scan) for s in strategies]
    values = [v for v in values if v is not None]
    if len(values) == 0:
        return None

    result = sum(values) / len(values)
    return result
