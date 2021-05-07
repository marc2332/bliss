# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
from typing import NamedTuple

import weakref
import logging
from ..model import scan_model
from ..model import plot_model
from ..model import plot_item_model
from . import model_helper
from bliss.controllers.lima import roi as lima_roi


_logger = logging.getLogger(__name__)


class ChannelInfo(NamedTuple):
    name: str
    info: Dict
    device: str
    master: str


_SCAN_CATEGORY = {
    # A single measurement
    "ct": "point",
    # Many measurements
    "timescan": "nscan",
    "loopscan": "nscan",
    "lookupscan": "nscan",
    "pointscan": "nscan",
    "ascan": "nscan",
    "a2scan": "nscan",
    "a3scan": "nscan",
    "a4scan": "nscan",
    "anscan": "nscan",
    "dscan": "nscan",
    "d2scan": "nscan",
    "d3scan": "nscan",
    "d4scan": "nscan",
    "dnscan": "nscan",
    # Many measurements using 2 correlated axes
    "amesh": "mesh",
    "dmesh": "mesh",
}


def get_scan_category(scan_info: Dict = None, scan_type: str = None) -> Optional[str]:
    """
    Returns a scan category for the given scan_info.

    Returns:
        One of "point", "nscan", "mesh" or None if nothing matches.
    """
    if scan_info is not None:
        scan_type = scan_info.get("type", None)
    return _SCAN_CATEGORY.get(scan_type, None)


def _get_channels(
    scan_info: Dict, top_master_name: str = None, dim: int = None, master: bool = None
):
    """
    Returns channels from top_master_name and optionally filtered by dim and master.

    Channels from masters are listed first, and the channel order stays the same.

    Arguments:
        scan_info: Scan info dict
        top_master_name: If not None, a specific top master is read
        dim: If not None, only includes the channels with the requested dim
        master: If not None, only includes channels from a master / or not
    """
    names = []

    master_count = 0
    for top_master, meta in scan_info["acquisition_chain"].items():
        if top_master_name is not None:
            if top_master != top_master_name:
                # If the filter mismatch
                continue
        devices = meta["devices"]
        for device_name in devices:
            device_info = scan_info["devices"].get(device_name, None)
            if device_info is None:
                continue

            if master is not None:
                is_triggering = "triggered_devices" in device_info
                if is_triggering:
                    master_count += 1
                is_master = is_triggering and master_count == 1
                if master ^ is_master:
                    # If the filter mismatch
                    continue

            for c in device_info.get("channels", []):
                if dim is not None:
                    if scan_info["channels"].get(c, {}).get("dim", 0) != dim:
                        # If the filter mismatch
                        continue
                names.append(c)

    return names


def iter_channels(scan_info: Dict[str, Any]):
    acquisition_chain_description = scan_info.get("acquisition_chain", {})
    channels_description = scan_info.get("channels", {})

    def get_device_from_channel_name(channel_name):
        """Returns the device name from the channel name, else None"""
        if ":" in channel_name:
            return channel_name.rsplit(":", 1)[0]
        return None

    channels = set([])

    for master_name in acquisition_chain_description.keys():
        master_channels = _get_channels(scan_info, master_name)
        for channel_name in master_channels:
            info = channels_description.get(channel_name, {})
            device_name = get_device_from_channel_name(channel_name)
            channel = ChannelInfo(channel_name, info, device_name, master_name)
            yield channel
            channels.add(channel_name)

    requests = scan_info.get("channels", {})
    if not isinstance(requests, dict):
        _logger.warning("scan_info.requests is not a dict")
        requests = {}

    for channel_name, info in requests.items():
        if channel_name in channels:
            continue
        device_name = get_device_from_channel_name(channel_name)
        # FIXME: For now, let say everything is scalar here
        channel = ChannelInfo(channel_name, info, device_name, "custom")
        yield channel


def create_scan_model(scan_info: Dict) -> scan_model.Scan:
    is_group = scan_info.get("is-scan-sequence", False)
    if is_group:
        scan = scan_model.ScanGroup()
    else:
        scan = scan_model.Scan()
    scan.setScanInfo(scan_info)

    devices: Dict[str, scan_model.Device] = {}
    channel_units = read_units(scan_info)
    channel_display_names = read_display_names(scan_info)

    def get_device(master_name, device_name):
        """Returns the device object.

        Create it if it is not yet available.
        """
        if device_name is None:
            key = master_name
            master = devices.get(key, None)
            if master is None:
                # Master have to be created
                master = scan_model.Device(scan)
                master.setName(master_name)
                devices[key] = master
            return master

        key = master_name + ":" + device_name
        device = devices.get(key, None)
        if device is None:
            if ":" in device_name:
                parent_device_name, name = device_name.rsplit(":", 1)
                parent = get_device(master_name, parent_device_name)
            else:
                name = device_name
                parent = get_device(master_name, None)
            device = scan_model.Device(scan)
            device.setName(name)
            device.setMaster(parent)
            devices[key] = device
        return device

    def create_virtual_roi(roi_name, key, parent):
        device = scan_model.Device(scan)
        device.setName(roi_name)
        device.setMaster(parent)
        device.setType(scan_model.DeviceType.VIRTUAL_ROI)

        # Read metadata
        roi_dict = scan_info.get("rois", {}).get(key)
        roi = None
        if roi_dict is not None:
            try:
                roi = lima_roi.dict_to_roi(roi_dict)
            except Exception:
                _logger.warning("Error while reading roi '%s'", key, exc_info=True)

        metadata = scan_model.DeviceMetadata(roi)
        device.setMetadata(metadata)
        return device

    channelsDict = {}
    channels = iter_channels(scan_info)
    for channel_info in channels:
        master_name = channel_info.master
        device_name = channel_info.device
        parent = get_device(master_name, device_name)
        name = channel_info.name
        short_name = name.rsplit(":")[-1]

        # Some magic to create virtual device for each ROIs
        if parent.name() in ["roi_counters", "roi_profiles"]:
            # guess the computation part do not contain _
            # FIXME: It would be good to have a real ROI concept in BLISS
            if "_" in short_name:
                roi_name, _ = short_name.rsplit("_", 1)
            else:
                roi_name = short_name
            key = f"{channel_info.device}:{roi_name}"
            device = devices.get(key, None)
            if device is None:
                device = create_virtual_roi(roi_name, key, parent)
                devices[key] = device
            parent = device

        channel = scan_model.Channel(parent)
        channelsDict[channel_info.name] = channel
        channel.setName(name)
        unit = channel_units.get(channel_info.name, None)
        if unit is not None:
            channel.setUnit(unit)
        display_name = channel_display_names.get(channel_info.name, None)
        if display_name is not None:
            channel.setDisplayName(display_name)

    scatterDataDict: Dict[str, scan_model.ScatterData] = {}
    channels = scan_info.get("channels", None)
    if channels:
        for channel_name, metadata_dict in channels.items():
            channel = channelsDict.get(channel_name, None)
            if channel is not None:
                metadata = parse_channel_metadata(metadata_dict)
                channel.setMetadata(metadata)
                if metadata.group is not None:
                    scatterData = scatterDataDict.get(metadata.group, None)
                    if scatterData is None:
                        scatterData = scan_model.ScatterData()
                        scatterDataDict[metadata.group] = scatterData
                    if (
                        channel.metadata().axisKind is not None
                        or channel.metadata().axisId is not None
                    ):
                        scatterData.addAxisChannel(channel, metadata.axisId)
                    else:
                        scatterData.addCounterChannel(channel)
            else:
                _logger.warning(
                    "Channel %s is part of the request but not part of the acquisition chain. Info ignored",
                    channel_name,
                )

    for scatterData in scatterDataDict.values():
        scan.addScatterData(scatterData)

    scan.seal()
    return scan


def read_units(scan_info: Dict) -> Dict[str, str]:
    """Merge all units together"""
    if "channels" not in scan_info:
        return {}
    result = {k: v["unit"] for k, v in scan_info["channels"].items() if "unit" in v}
    return result


def read_display_names(scan_info: Dict) -> Dict[str, str]:
    """Merge all display names together"""
    if "channels" not in scan_info:
        return {}
    result = {
        k: v["display_name"]
        for k, v in scan_info["channels"].items()
        if "display_name" in v
    }
    return result


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
    axisPointsHint = _pop_and_convert(meta, "axis-points-hint", int)
    axisKind = _pop_and_convert(meta, "axis-kind", scan_model.AxisKind)
    axisId = _pop_and_convert(meta, "axis-id", int)
    group = _pop_and_convert(meta, "group", str)
    dim = _pop_and_convert(meta, "dim", int)

    # Compatibility code with existing user scripts written for BLISS 1.4
    mapping = {
        scan_model.AxisKind.FAST: (0, scan_model.AxisKind.FORTH),
        scan_model.AxisKind.FAST_BACKNFORTH: (0, scan_model.AxisKind.BACKNFORTH),
        scan_model.AxisKind.SLOW: (1, scan_model.AxisKind.FORTH),
        scan_model.AxisKind.SLOW_BACKNFORTH: (1, scan_model.AxisKind.BACKNFORTH),
    }
    if axisKind in mapping:
        if axisId is not None:
            _logger.warning(
                "Both axis-id and axis-kind with flat/slow is used. axis-id will be ignored"
            )
        axisId, axisKind = mapping[axisKind]

    for key in meta.keys():
        _logger.warning("Metadata key %s is unknown. Field ignored.", key)

    return scan_model.ChannelMetadata(
        start,
        stop,
        vmin,
        vmax,
        points,
        axisId,
        axisPoints,
        axisKind,
        group,
        axisPointsHint,
        dim,
    )


def get_device_from_channel(channel_name) -> str:
    elements = channel_name.split(":")
    return elements[0]


def _select_default_counter(scan, plot):
    """Select a default counter if needed."""
    for item in plot.items():
        if isinstance(item, plot_item_model.ScatterItem):
            if item.valueChannel() is None:
                # If there is an axis but no value
                # Pick a value
                axisChannelRef = item.xChannel()
                if axisChannelRef is None:
                    axisChannelRef = item.yChannel()
                if axisChannelRef is None:
                    continue
                axisChannel = axisChannelRef.channel(scan)

                scatterData = scan.getScatterDataByChannel(axisChannel)
                names: List[str]
                if scatterData is not None:
                    counters = scatterData.counterChannels()
                    names = [c.name() for c in counters]
                else:
                    acquisition_chain = scan.scanInfo().get("acquisition_chain", None)
                    names = []
                    if acquisition_chain is not None:
                        for master_name in acquisition_chain.keys():
                            counter_scalars = _get_channels(
                                scan.scanInfo(), master_name, master=False, dim=0
                            )
                            names.extend(counter_scalars)
                if len(names) > 0:
                    # Try to use a default counter which is not an elapse time
                    quantityNames = [
                        n for n in names if scan.getChannelByName(n).unit() != "s"
                    ]
                    if len(quantityNames) > 0:
                        names = quantityNames
                    channelRef = plot_model.ChannelRef(plot, names[0])
                    item.setValueChannel(channelRef)


class DisplayExtra(NamedTuple):
    displayed_channels: Optional[List[str]]
    plotselect: Optional[List[str]]


def parse_display_extra(scan_info: Dict) -> DisplayExtra:
    """Return the list of the displayed channels stored in the scan"""

    def parse_optional_list_of_string(data, name):
        """Sanitize data from scan_info protocol"""
        if data is None:
            return None

        if not isinstance(data, list):
            _logger.warning("%s is not a list: Key ignored", name)
            return None

        if not all([isinstance(i, str) for i in data]):
            _logger.warning("%s must only contains strings: Key ignored", name)
            return None

        return data

    display_extra = scan_info.get("_display_extra", None)
    if display_extra is not None:
        raw = display_extra.get("displayed_channels", None)
        displayed_channels = parse_optional_list_of_string(
            raw, "_display_extra.displayed_channels"
        )
        raw = display_extra.get("plotselect", None)
        plotselect = parse_optional_list_of_string(raw, "_display_extra.plotselect")
    else:
        displayed_channels = None
        plotselect = None
    return DisplayExtra(displayed_channels, plotselect)


def removed_same_plots(plots, remove_plots) -> List[plot_model.Plot]:
    """Returns plots from an initial list of `plots` in which same plots was
    removed."""
    if remove_plots == []:
        return list(plots)
    result = []
    for p in plots:
        for p2 in remove_plots:
            if p.hasSameTarget(p2):
                break
        else:
            result.append(p)
            continue
    return result


def create_plot_model(
    scan_info: Dict, scan: Optional[scan_model.Scan] = None
) -> List[plot_model.Plot]:
    """Create plot models from a scan_info.

    Use the `plots` description or infer the plots from the `acquisition_chain`.
    Finally update the selection using `_display_extra`.
    """
    if "plots" in scan_info:
        plots = read_plot_models(scan_info)
        for plot in plots:
            _select_default_counter(scan, plot)

        def contains_default_plot_kind(plots, plot):
            """Returns true if the list contain a default plot for this kind."""
            for p in plots:
                if p.hasSameTarget(plot):
                    return True
            return False

        aq_plots = infer_plot_models(scan_info)
        for plot in aq_plots:
            if not contains_default_plot_kind(plots, plot):
                plots.append(plot)
    else:
        plots = infer_plot_models(scan_info)

    def filter_with_scan_content(channel_names, scan):
        if scan is None:
            return channel_names
        if channel_names is None:
            return channel_names
        # Filter selection by available channels
        intersection = set(channel_names) & set(scan.getChannelNames())
        if len(channel_names) != len(intersection):
            # Remove missing without breaking the order
            for name in list(channel_names):
                if name not in intersection:
                    channel_names.remove(name)
                    _logger.warning(
                        "Skip display of channel '%s' from scan_info. Not part of the scan",
                        name,
                    )
            if len(channel_names) == 0:
                channel_names = None
        return channel_names

    display_extra = parse_display_extra(scan_info)
    displayed_channels = filter_with_scan_content(
        display_extra.displayed_channels, scan
    )

    for plot in plots:
        channel_names = None
        if isinstance(plot, plot_item_model.CurvePlot):
            if displayed_channels is None:
                channel_names = filter_with_scan_content(display_extra.plotselect, scan)
            else:
                channel_names = displayed_channels
        elif isinstance(plot, plot_item_model.ScatterPlot):
            if displayed_channels:
                channel_names = displayed_channels
        if channel_names:
            model_helper.updateDisplayedChannelNames(plot, scan, channel_names)

    return plots


def read_plot_models(scan_info: Dict) -> List[plot_model.Plot]:
    """Read description of plot models from a scan_info"""
    result: List[plot_model.Plot] = []

    plots = scan_info.get("plots", None)
    if not isinstance(plots, list):
        return []

    for plot_description in plots:
        if not isinstance(plot_description, dict):
            _logger.warning("Plot description is not a dict. Skipped.")
            continue

        kind = plot_description.get("kind", None)
        if kind != "scatter-plot":
            _logger.warning("Kind %s unsupported. Skipped.", kind)
            continue

        plot = plot_item_model.ScatterPlot()

        name = plot_description.get("name", None)
        if name is not None:
            plot.setName(name)

        items = plot_description.get("items", None)
        if not isinstance(items, list):
            _logger.warning("'items' not using the right type. List expected. Ignored.")
            items = []

        for item_description in items:
            kind = item_description.get("kind", None)
            if kind == "scatter":
                item = plot_item_model.ScatterItem(plot)

                xname = item_description.get("x", None)
                if xname is not None:
                    x_channel = plot_model.ChannelRef(plot, xname)
                    item.setXChannel(x_channel)
                yname = item_description.get("y", None)
                if yname is not None:
                    y_channel = plot_model.ChannelRef(plot, yname)
                    item.setYChannel(y_channel)
                valuename = item_description.get("value", None)
                if valuename is not None:
                    value_channel = plot_model.ChannelRef(plot, valuename)
                    item.setValueChannel(value_channel)
                plot.addItem(item)
            else:
                _logger.warning("Item 'kind' %s unsupported. Item ignored.", kind)
        result.append(plot)

    return result


def _infer_default_curve_plot(
    scan_info: Dict, have_scatter: bool
) -> Optional[plot_model.Plot]:
    """Create a curve plot by inferring the acquisition chain content.

    If there is a scatter as main plot, try to use a time counter as axis.
    """
    plot = plot_item_model.CurvePlot()

    def get_unit(channel_name: str) -> Optional[str]:
        return scan_info["channels"][channel_name].get("unit", None)

    acquisition_chain = scan_info.get("acquisition_chain", None)
    for master_name in acquisition_chain.keys():
        scalars = _get_channels(scan_info, master_name, dim=0, master=False)
        master_channels = _get_channels(scan_info, master_name, dim=0, master=True)

        if have_scatter:
            # In case of scatter the curve plot have to plot the time in x
            # Masters in y1 and the first value in y2

            for timer in scalars:
                if timer in master_channels:
                    # skip the masters
                    continue
                if get_unit(timer) != "s":
                    # skip non time base
                    continue
                break
            else:
                timer = None

            for scalar in scalars:
                if scalar in master_channels:
                    # skip the masters
                    continue
                if get_unit(scalar) == "s":
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
            if len(master_channels) > 0 and master_channels[0].startswith("axis:"):
                master_channel = master_channels[0]
                master_channel_unit = get_unit(master_channel)
                is_motor_scan = master_channel_unit != "s"
            else:
                is_motor_scan = False

            for channel_name in scalars:
                if is_motor_scan and get_unit(channel_name) == "s":
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
                # Only display the first counter
                break
    return plot


def _infer_default_scatter_plot(scan_info: Dict) -> List[plot_model.Plot]:
    """Create a set of scatter plots according to the content of acquisition
    chain"""
    plots: List[plot_model.Plot] = []

    def get_unit(channel_name: str) -> Optional[str]:
        return scan_info["channels"][channel_name].get("unit", None)

    acquisition_chain = scan_info.get("acquisition_chain", None)

    for master_name in acquisition_chain.keys():
        plot = plot_item_model.ScatterPlot()

        scalars = _get_channels(scan_info, master_name, dim=0, master=False)
        axes_channels = _get_channels(scan_info, master_name, dim=0, master=True)

        # Reach the first scalar which is not a time unit
        for scalar in scalars:
            if scalar in axes_channels:
                # skip the masters
                continue
            if get_unit(scalar) == "s":
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
        plot.addItem(item)
        plots.append(plot)

    return plots


def infer_plot_models(scan_info: Dict) -> List[plot_model.Plot]:
    """Infer description of plot models from a scan_info using
    `acquisition_chain`.

    - Dedicated default plot is created for 0D channels according to the kind
      of scan. It could be:
        - ct plot
        - curve plot
        - scatter plot
    - A dedicated image plot is created per lima detectors
    - A dedicated MCA plot is created per mca detectors
    - Remaining 2D channels are displayed as an image widget
    - Remaining 1D channels are displayed as a 1D plot
    """
    result: List[plot_model.Plot] = []

    default_plot = None

    acquisition_chain = scan_info.get("acquisition_chain", None)
    if len(acquisition_chain.keys()) == 1:
        first_key = list(acquisition_chain.keys())[0]
        if first_key == "GroupingMaster":
            # Make sure groups does not generate any plots
            return []

    # ct / curve / scatter

    if scan_info.get("type", None) == "ct":
        plot = plot_item_model.ScalarPlot()
        result.append(plot)
    else:
        have_scalar = False
        have_scatter = False
        for master_name in acquisition_chain.keys():
            scalars = _get_channels(scan_info, master_name, dim=0, master=False)
            if len(scalars) > 0:
                have_scalar = True
            if scan_info.get("data_dim", 1) == 2 or scan_info.get("dim", 1) == 2:
                have_scatter = True

        if have_scalar:
            plot = _infer_default_curve_plot(scan_info, have_scatter)
            if plot is not None:
                result.append(plot)
                if not have_scalar:
                    default_plot = plot
        if have_scatter:
            plots = _infer_default_scatter_plot(scan_info)
            if len(plots) > 0:
                result.extend(plots)
                if default_plot is None:
                    default_plot = plots[0]

    # MCA devices

    for device_id, device_info in scan_info.get("devices", {}).items():
        device_type = device_info.get("type")
        device_name = device_id.rsplit(":", 1)[-1]

        if device_type != "mca":
            continue

        plot = None

        for channel_name in device_info.get("channels", []):
            channel_info = scan_info["channels"].get(channel_name, {})
            dim = channel_info.get("dim", 0)
            if dim != 1:
                continue

            if plot is None:
                plot = plot_item_model.McaPlot()
                plot.setDeviceName(device_name)
                if default_plot is None:
                    default_plot = plot

            channel = plot_model.ChannelRef(plot, channel_name)
            item = plot_item_model.McaItem(plot)
            item.setMcaChannel(channel)

            plot.addItem(item)

        if plot is not None:
            result.append(plot)

    # Other 1D devices

    for device_id, device_info in scan_info.get("devices", {}).items():
        device_type = device_info.get("type")
        device_name = device_id.rsplit(":", 1)[-1]

        if device_type == "mca":
            continue

        plot = None

        for channel_name in device_info.get("channels", []):
            channel_info = scan_info["channels"].get(channel_name, {})
            dim = channel_info.get("dim", 0)
            if dim != 1:
                continue

            if plot is None:
                # In case of Lima roi_counter, it is easier to reach the device
                # name this way for now
                device_fullname = get_device_from_channel(channel_name)
                plot = plot_item_model.OneDimDataPlot()
                plot.setDeviceName(device_fullname)
                if default_plot is None:
                    default_plot = plot

            channel = plot_model.ChannelRef(plot, channel_name)
            item = plot_item_model.CurveItem(plot)
            item.setYChannel(channel)
            # FIXME: Have to be properly setup with a concept of arange
            item.setXChannel(channel)

            plot.addItem(item)

        if plot is not None:
            result.append(plot)

    # Image plot

    for master_name in acquisition_chain.keys():
        for device_id in acquisition_chain[master_name].get("devices", []):
            device_info = scan_info["devices"].get(device_id, {})
            device_type = device_info.get("type")
            device_name = device_id.rsplit(":", 1)[-1]
            plot = None

            for channel_name in device_info.get("channels", []):
                channel_info = scan_info["channels"].get(channel_name, {})
                dim = channel_info.get("dim", 0)
                if dim != 2:
                    continue

                if plot is None:
                    plot = plot_item_model.ImagePlot()
                    device_name = get_device_from_channel(channel_name)
                    plot.setDeviceName(device_name)
                    if default_plot is None:
                        default_plot = plot
                    if device_type == "lima":
                        if "rois" in scan_info:
                            for roi_name, _roi_dict in scan_info["rois"].items():
                                if not roi_name.startswith(
                                    f"{device_name}:roi_counters:"
                                ) and not roi_name.startswith(
                                    f"{device_name}:roi_profiles:"
                                ):
                                    pass
                                item = plot_item_model.RoiItem(plot)
                                item.setDeviceName(f"{master_name}:{roi_name}")
                                plot.addItem(item)

                image_channel = plot_model.ChannelRef(plot, channel_name)
                item = plot_item_model.ImageItem(plot)
                item.setImageChannel(image_channel)
                plot.addItem(item)

            if plot is not None:
                result.append(plot)

    # Move the default plot on top
    if default_plot is not None:
        result.remove(default_plot)
        result.insert(0, default_plot)

    return result


def get_full_title(scan: scan_model.Scan) -> str:
    """Returns from scan_info a readable title"""
    scan_info = scan.scanInfo()
    if scan_info is None:
        return "No scan title"
    title = scan_info.get("title", "No scan title")
    scan_nb = scan_info.get("scan_nb", None)
    if scan_nb is not None:
        text = f"{title} (#{scan_nb})"
    else:
        text = f"{title}"
    return text


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


_PROGRESS_STRATEGIES: MutableMapping[
    scan_model.Scan, List[_ProgressStrategy]
] = weakref.WeakKeyDictionary()


class _ProgressOfAnyChannels(_ProgressStrategy):
    """Compute the progress according to any of the available channels"""

    def __init__(self, maxPoints: int):
        self.__maxPoints = maxPoints

    def compute(self, scan: scan_model.Scan) -> Optional[float]:
        scan_info = scan.scanInfo()
        master_channels: List[str] = []
        for channel_name, meta in scan_info["channels"].items():
            dim = meta.get("dim", 0)
            if dim in [0, 2]:
                master_channels.append(channel_name)

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


class _ProgressOfSequence(_ProgressStrategy):
    def __init__(self, scan: scan_model.Scan):
        super(_ProgressOfSequence, self).__init__()
        scanInfo = scan.scanInfo()
        sequenceInfo = scanInfo.get("sequence-info", {})
        scanCount = sequenceInfo.get("scan-count", None)
        if isinstance(scanCount, int) and scanCount > 0:
            self.__scanCount = scanCount
        else:
            self.__scanCount = None

    def compute(self, scan: scan_model.Scan) -> Optional[float]:
        if self.__scanCount is None:
            return None

        subScans = scan.subScans()
        return len(subScans) / self.__scanCount


def _create_progress_strategies(scan: scan_model.Scan) -> List[_ProgressStrategy]:
    scan_info = scan.scanInfo()
    if scan_info is None:
        return []

    strategies = []

    if isinstance(scan, scan_model.ScanGroup):
        strategy = _ProgressOfSequence(scan)
        strategies.append(strategy)

    channels = scan_info.get("channels", None)
    if channels:
        # Reach on channel per npoints (in case of many top masters without
        # same size)
        strategy_per_npoints: Dict[int, _ProgressStrategy] = {}
        for channel_name, metadata_dict in channels.items():
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

    Returns a value between 0..1, else None if it is not applicable.
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


class PositionerDescription(NamedTuple):
    name: str
    start: float
    end: float
    dial_start: float
    dial_end: float
    units: str


def get_all_positioners(scan_info: Dict) -> List[PositionerDescription]:
    result = []
    positioners = scan_info.get("positioners", None)
    if positioners is None:
        return result

    def zipdict(*args):
        keys = []
        for d in args:
            if d is not None:
                for k in d.keys():
                    #  Add keys in a conservative order
                    if k not in keys:
                        keys.append(k)
        for k in keys:
            result = [k]
            for d in args:
                if d is None:
                    v = None
                else:
                    v = d.get(k, None)
                result.append(v)
            yield result

    positioners_dial_start = positioners.get("positioners_dial_start", None)
    positioners_dial_end = positioners.get("positioners_dial_end", None)
    positioners_start = positioners.get("positioners_start", None)
    positioners_end = positioners.get("positioners_end", None)
    positioners_units = positioners.get("positioners_units", None)
    meta = [
        positioners_start,
        positioners_end,
        positioners_dial_start,
        positioners_dial_end,
        positioners_units,
    ]
    for key, start, end, dial_start, dial_end, units in zipdict(*meta):
        p = PositionerDescription(key, start, end, dial_start, dial_end, units)
        result.append(p)
    return result


def is_same(scan_info1: Dict, scan_info2: Dict) -> bool:
    """Returns true if both scans have the same structure

    This function check the type of the scan and it's masters
    """
    type1 = scan_info1.get("type", None)
    type2 = scan_info2.get("type", None)
    if type1 != type2:
        return False
    masters1 = _get_channels(scan_info1, master=True)
    masters2 = _get_channels(scan_info2, master=True)
    return masters1 == masters2
