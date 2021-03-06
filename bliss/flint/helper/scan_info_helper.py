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

import numpy
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


class ScanModelReader:
    """Object reading a scan_info and generating a scan model"""

    DEVICE_TYPES = {
        None: scan_model.DeviceType.NONE,
        "lima": scan_model.DeviceType.LIMA,
        "mca": scan_model.DeviceType.MCA,
    }

    def __init__(self, scan_info):
        self._scan_info = scan_info
        self._acquisition_chain_description = scan_info.get("acquisition_chain", {})
        self._device_description = scan_info.get("devices", {})
        self._channel_description = scan_info.get("channels", {})

        scan_info = self._scan_info
        is_group = scan_info.get("is-scan-sequence", False)
        if is_group:
            scan = scan_model.ScanGroup()
        else:
            scan = scan_model.Scan()

        scan.setScanInfo(scan_info)
        self._scan = scan
        self._parsed_devices = set()

    def parse(self):
        """Parse the whole scan info and return scan model"""
        assert self._scan is not None, "The scan was already parsed"
        self._parse_scan()
        self._precache_scatter_constraints()
        scan = self._scan
        self._scan = None
        scan.seal()
        return scan

    def _parse_scan(self):
        """Parse the whole scan structure"""
        for top_master_name, meta in self._acquisition_chain_description.items():
            self._parse_top_device(top_master_name, meta)

    def _parse_top_device(self, name, meta) -> scan_model.Device:
        top_master = scan_model.Device(self._scan)
        top_master.setName(name)

        sub_device_names = meta["devices"]

        for i, sub_device_name in enumerate(sub_device_names):
            if sub_device_name in self._parsed_devices:
                continue
            self._parsed_devices.add(sub_device_name)
            sub_meta = self._device_description.get(sub_device_name, None)
            if sub_meta is None:
                _logger.error(
                    "scan_info mismatch. Device name %s metadata not found",
                    sub_device_name,
                )
                continue
            sub_name = sub_device_name.rsplit(":", 1)[-1]
            if i == 0:
                parser_class = self.TopDeviceParser
            else:
                parser_class = None
            self._parse_device(
                sub_name, sub_meta, parent=top_master, parser_class=parser_class
            )

    class DefaultDeviceParser:
        def __init__(self, reader):
            self.reader = reader

        def parse(self, name, meta, parent):
            device = self.create_device(name, meta, parent)
            self.parse_sub_devices(device, meta)
            self.parse_channels(device, meta)

        def create_device(self, name, meta, parent):
            device = scan_model.Device(self.reader._scan)
            device.setName(name)
            device.setMaster(parent)
            device_type = meta.get("type", None)
            device_type = self.reader.DEVICE_TYPES.get(
                device_type, scan_model.DeviceType.UNKNOWN
            )
            device.setType(device_type)
            metadata = scan_model.DeviceMetadata(info=meta, roi=None)
            device.setMetadata(metadata)
            return device

        def parse_sub_devices(self, device, meta):
            device_ids = meta.get("triggered_devices", [])
            for device_id in device_ids:
                self.reader._parsed_devices.add(device_id)
                sub_meta = self.reader._device_description.get(device_id, None)
                if sub_meta is None:
                    _logger.error(
                        "scan_info mismatch. Device name %s metadata not found",
                        device_id,
                    )
                    continue
                sub_name = device_id.rsplit(":", 1)[-1]
                self.reader._parse_device(sub_name, sub_meta, parent=device)

        def parse_channels(self, device: scan_model.Device, meta):
            channel_names = meta.get("channels", [])
            for channel_fullname in channel_names:
                channel_meta = self.reader._channel_description.get(
                    channel_fullname, None
                )
                if channel_meta is None:
                    _logger.error(
                        "scan_info mismatch. Channel name %s metadata not found",
                        channel_fullname,
                    )
                    continue
                self.parse_channel(channel_fullname, channel_meta, parent=device)

            xaxis_array = meta.get("xaxis_array", None)
            if xaxis_array is not None:
                # Create a virtual channel already feed with data
                try:
                    xaxis_array = numpy.array(xaxis_array)
                    if len(xaxis_array.shape) != 1:
                        raise RuntimeError("scan_info xaxis_array expect a 1D data")
                except Exception:
                    _logger.warning(
                        "scan_info contains wrong xaxis_array: %s", xaxis_array
                    )
                    xaxis_array = numpy.array([])

                unit = meta.get("xaxis_array_unit", None)
                label = meta.get("xaxis_array_label", None)
                channel = scan_model.Channel(device)
                channel.setType(scan_model.ChannelType.SPECTRUM)
                if unit is not None:
                    channel.setUnit(unit)
                if label is not None:
                    channel.setDisplayName(label)
                data = scan_model.Data(array=xaxis_array)
                channel.setData(data)
                fullname = device.name()
                channel.setName(f"{fullname}:#:xaxis_array")

        def parse_channel(self, channel_fullname: str, meta, parent: scan_model.Device):
            channel = scan_model.Channel(parent)
            channel.setName(channel_fullname)

            # protect mutation of the original object, with the following `pop`
            meta = dict(meta)

            # FIXME: This have to be cleaned up (unit and display name are part of the metadata)
            unit = meta.pop("unit", None)
            if unit is not None:
                channel.setUnit(unit)
            display_name = meta.pop("display_name", None)
            if display_name is not None:
                channel.setDisplayName(display_name)

            metadata = parse_channel_metadata(meta)
            channel.setMetadata(metadata)

    class TopDeviceParser(DefaultDeviceParser):
        def parse_sub_devices(self, device, meta):
            # Ignore sub devices to make it a bit more flat
            pass

    class LimaRoiDeviceParser(DefaultDeviceParser):
        def parse_channels(self, device: scan_model.Device, meta: Dict):

            # cache virtual roi devices
            virtual_rois = {}

            # FIXME: It would be good to have a real ROI concept in BLISS
            # Here we iterate the set of metadata to try to find something interesting
            for roi_name, roi_dict in meta.items():
                if not isinstance(roi_dict, dict):
                    continue
                if "kind" not in roi_dict:
                    continue
                roi_device = self.create_virtual_roi(roi_name, roi_dict, device)
                virtual_rois[roi_name] = roi_device

            def get_virtual_roi(channel_fullname):
                """Retrieve roi device from channel name"""
                nonlocal virtual_rois
                short_name = channel_fullname.rsplit(":", 1)[-1]

                if "_" in short_name:
                    roi_name, _ = short_name.rsplit("_", 1)
                else:
                    roi_name = short_name

                return virtual_rois.get(roi_name, None)

            channel_names = meta.get("channels", [])
            for channel_fullname in channel_names:
                channel_meta = self.reader._channel_description.get(
                    channel_fullname, None
                )
                if channel_meta is None:
                    _logger.error(
                        "scan_info mismatch. Channel name %s metadata not found",
                        channel_fullname,
                    )
                    continue
                roi_device = get_virtual_roi(channel_fullname)
                if roi_device is not None:
                    parent_channel = roi_device
                else:
                    parent_channel = device
                self.parse_channel(
                    channel_fullname, channel_meta, parent=parent_channel
                )

        def create_virtual_roi(self, roi_name, roi_dict, parent):
            device = scan_model.Device(self.reader._scan)
            device.setName(roi_name)
            device.setMaster(parent)
            device.setType(scan_model.DeviceType.VIRTUAL_ROI)

            # Read metadata
            roi = None
            if roi_dict is not None:
                try:
                    roi = lima_roi.dict_to_roi(roi_dict)
                except Exception:
                    _logger.warning(
                        "Error while reading roi '%s' from '%s'",
                        roi_name,
                        device.fullName(),
                        exc_info=True,
                    )

            metadata = scan_model.DeviceMetadata({}, roi)
            device.setMetadata(metadata)
            return device

    class McaDeviceParser(DefaultDeviceParser):
        def parse_channels(self, device, meta):
            # cache virtual roi devices
            virtual_detectors = {}

            def get_virtual_detector(channel_fullname):
                """Some magic to create virtual device for each ROIs"""
                short_name = channel_fullname.rsplit(":", 1)[-1]

                # FIXME: It would be good to have a real detector concept in BLISS
                if "_" in short_name:
                    _, detector_name = short_name.rsplit("_", 1)
                else:
                    detector_name = short_name

                key = f"{device.name()}:{detector_name}"
                if key in virtual_detectors:
                    return virtual_detectors[key]

                detector_device = scan_model.Device(self.reader._scan)
                detector_device.setName(detector_name)
                detector_device.setMaster(device)
                detector_device.setType(scan_model.DeviceType.VIRTUAL_MCA_DETECTOR)
                virtual_detectors[key] = detector_device
                return detector_device

            channel_names = meta.get("channels", [])
            for channel_fullname in channel_names:
                channel_meta = self.reader._channel_description.get(
                    channel_fullname, None
                )
                if channel_meta is None:
                    _logger.error(
                        "scan_info mismatch. Channel name %s metadata not found",
                        channel_fullname,
                    )
                    continue
                roi_device = get_virtual_detector(channel_fullname)
                self.parse_channel(channel_fullname, channel_meta, parent=roi_device)

    def _parse_device(
        self, name: str, meta: Dict, parent: scan_model.Device, parser_class=None
    ):
        if parent.type() == scan_model.DeviceType.LIMA:
            if name == "roi_counters" or name == "roi_profiles":
                parser_class = self.LimaRoiDeviceParser
        if parser_class is None:
            device_type = meta.get("type")
            if device_type == "mca":
                parser_class = self.McaDeviceParser
            else:
                parser_class = self.DefaultDeviceParser

        node_parser = parser_class(self)
        node_parser.parse(name, meta, parent=parent)

    def _precache_scatter_constraints(self):
        """Precache information about group of data and available scatter axis"""
        scan = self._scan
        scatterDataDict: Dict[str, scan_model.ScatterData] = {}
        for device in scan.devices():
            for channel in device.channels():
                metadata = channel.metadata()
                if metadata.group is not None:
                    scatterData = scatterDataDict.get(metadata.group, None)
                    if scatterData is None:
                        scatterData = scan_model.ScatterData()
                        scatterDataDict[metadata.group] = scatterData
                    if metadata.axisKind is not None or metadata.axisId is not None:
                        scatterData.addAxisChannel(channel, metadata.axisId)
                    else:
                        scatterData.addCounterChannel(channel)

        for scatterData in scatterDataDict.values():
            scan.addScatterData(scatterData)


def create_scan_model(scan_info: Dict) -> scan_model.Scan:
    reader = ScanModelReader(scan_info)
    scan = reader.parse()
    return scan


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
    """Enforced list of channels to display for this specific scan"""

    plotselect: Optional[List[str]]
    """List of name selected by plot select"""

    plotselect_time: Optional[int]
    """Time from `time.time()` of the last plotselect"""


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
        plotselect_time = display_extra.get("plotselect_time", None)
    else:
        displayed_channels = None
        plotselect = None
        plotselect_time = None
    return DisplayExtra(displayed_channels, plotselect, plotselect_time)


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

    If a `plots` key exists from the `scan_info`, scatter and curve plots will
    created following this description. Else, plots will be inferred from the
    acquisition chain.

    Finally the selection is updated using `_display_extra` field. This should
    be removed a one point.

    Special kind of plots depending on devices and data kind, like Lima, MCAs
    and 1D data will always be inferred.
    """
    if scan is None:
        scan = create_scan_model(scan_info)

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

        aq_plots = infer_plot_models(scan)
        for plot in aq_plots:
            if isinstance(
                plot, (plot_item_model.CurvePlot, plot_item_model.ScatterPlot)
            ):
                # This kind of plots are already constrained by the `plots` key
                continue
            if not contains_default_plot_kind(plots, plot):
                plots.append(plot)
    else:
        plots = infer_plot_models(scan)

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


def _read_scatter_plot(plot_description: Dict) -> List[plot_model.Plot]:
    """Read a scatter plot definition from the scan_info"""
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
    return plot


def _read_curve_plot(plot_description: Dict) -> List[plot_model.Plot]:
    """Read a curve plot definition from the scan_info"""
    plot = plot_item_model.CurvePlot()

    name = plot_description.get("name", None)
    if name is not None:
        plot.setName(name)

    items = plot_description.get("items", None)
    if not isinstance(items, list):
        _logger.warning("'items' not using the right type. List expected. Ignored.")
        items = []

    for item_description in items:
        kind = item_description.get("kind", None)
        if kind == "curve":
            item = plot_item_model.CurveItem(plot)

            xname = item_description.get("x", None)
            if xname is not None:
                x_channel = plot_model.ChannelRef(plot, xname)
                item.setXChannel(x_channel)
            yname = item_description.get("y", None)
            if yname is not None:
                y_channel = plot_model.ChannelRef(plot, yname)
                item.setYChannel(y_channel)
            y_axis = item_description.get("y_axis", None)
            if y_axis in ("left", "right"):
                item.setYAxis(y_axis)
            plot.addItem(item)
        else:
            _logger.warning("Item 'kind' %s unsupported. Item ignored.", kind)
    return plot


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
        if kind == "scatter-plot":
            plot = _read_scatter_plot(plot_description)
        elif kind == "curve-plot":
            plot = _read_curve_plot(plot_description)
        else:
            _logger.warning("Kind %s unsupported. Skipped.", kind)
            continue

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


def _initialize_image_plot_from_device(device: scan_model.Device) -> plot_model.Plot:
    """Initialize ImagePlot with default information which can be used
    structurally"""
    plot = plot_item_model.ImagePlot()

    # Reach a name which is stable between 2 scans
    # FIXME: This have to be provided by the scan_info
    def get_stable_name(device):
        for channel in device.channels():
            name = channel.name()
            return name.rsplit(":", 1)[0]
        return device.fullName().split(":", 1)[1]

    stable_name = get_stable_name(device)
    plot.setDeviceName(stable_name)

    if device.type() == scan_model.DeviceType.LIMA:
        for sub_device in device.devices():
            if sub_device.name() in ["roi_counters", "roi_profiles"]:
                for roi_device in sub_device.devices():
                    if roi_device.type() != scan_model.DeviceType.VIRTUAL_ROI:
                        continue
                    item = plot_item_model.RoiItem(plot)
                    item.setDeviceName(roi_device.fullName())
                    plot.addItem(item)
    return plot


def infer_plot_models(scan: scan_model.Scan) -> List[plot_model.Plot]:
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
    scan_info = scan.scanInfo()

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

        xaxis_channel_name = device_info.get("xaxis_channel", None)
        xaxis_array = device_info.get("xaxis_array", None)
        if xaxis_channel_name is not None and xaxis_array is not None:
            _logger.warning(
                "Both xaxis_array and xaxis_channel are defined. xaxis_array will be ignored"
            )
            xaxis_array = None

        if xaxis_array is not None:
            xaxis_channel_name = f"{device_name}:#:xaxis_array"
            xaxis_array = None

        for channel_name in device_info.get("channels", []):
            channel_info = scan_info["channels"].get(channel_name, {})
            if channel_name == xaxis_channel_name:
                continue
            dim = channel_info.get("dim", 0)
            if dim != 1:
                continue

            if plot is None:
                plot = plot_item_model.OneDimDataPlot()

                # In case of Lima roi_counter, it is easier to reach the device
                # name this way for now
                device_fullname = get_device_from_channel(channel_name)
                device_root_name = device_fullname.split(":", 1)[0]
                if device_name == "roi_collection":
                    plot.setDeviceName(device_fullname)
                    plot.setPlotTitle(f"{device_root_name} (roi collection)")
                elif device_name == "roi_profile":
                    plot.setDeviceName(device_fullname)
                    plot.setPlotTitle(f"{device_root_name} (roi profiles)")
                else:
                    plot.setDeviceName(device_fullname)
                    plot.setPlotTitle(device_root_name)
                if default_plot is None:
                    default_plot = plot

            channel = plot_model.ChannelRef(plot, channel_name)

            if xaxis_channel_name is not None:
                item = plot_item_model.CurveItem(plot)
                item.setYChannel(channel)
                xchannel = plot_model.ChannelRef(plot, xaxis_channel_name)
                item.setXChannel(xchannel)
            else:
                item = plot_item_model.XIndexCurveItem(plot)
                item.setYChannel(channel)

            plot.addItem(item)

        if plot is not None:
            result.append(plot)

    # Image plot

    for device in scan.devices():
        plot = None
        for channel in device.channels():
            if channel.type() != scan_model.ChannelType.IMAGE:
                continue

            if plot is None:
                plot = _initialize_image_plot_from_device(device)
                if default_plot is None:
                    default_plot = plot

            image_channel = plot_model.ChannelRef(plot, channel.name())
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
                    # ??Add keys in a conservative order
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
