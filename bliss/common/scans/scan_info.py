# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Contains helper to manage the `scan_info` metadata provided inside each scans.
"""

import typing
import typeguard
import numbers


class ScanInfoFactory:
    """
    Factory to help to feed a `scan_info` dictionary.

    Argument:
        scan_info: The scan_info to feed
    """

    def __init__(self, scan_info: typing.Dict):
        self._scan_info = scan_info

    @typeguard.typechecked
    def set_channel_meta(
        self,
        name: str,
        start: typing.Optional[numbers.Real] = None,
        stop: typing.Optional[numbers.Real] = None,
        min: typing.Optional[numbers.Real] = None,
        max: typing.Optional[numbers.Real] = None,
        points: typing.Optional[numbers.Integral] = None,
        axis_points: typing.Optional[numbers.Integral] = None,
        axis_kind: typing.Optional[str] = None,
        group: typing.Optional[str] = None,
        axis_id: typing.Optional[numbers.Integral] = None,
        axis_points_hint: typing.Optional[numbers.Integral] = None,
    ):
        """
        Define metadata relative to a channel name

        Arguments:
            name: Name of the channel
            start: Start position of the axis
            stop: Stop position of the axis
            min: Minimal value the channel can have
            max: Minimal value the channel can have
            points: Amount of total points which will be transmitted by this channel
            axis_points: Amount of points for the axis (see scatter below)
            axis_kind: Kind of axis. It is used to speed up solid rendering in
                GUI. Can be one of:
                - `forth`: Move from start to stop always
                - `backnforth`: Move from start to stop to start
                - `step`: The motor position is discrete. The value can be used
                    to group data together.
            group: Specify a group for the channel. All the channels from the
                same group are supposed to contain the same amount of item at
                the end of the scan. It also can be used as a hint for
                interactive user selection.
            axis_id: Index of the axis in the scatter. 0 is the fastest.
            axis_points_hint: Number of approximate points expected in the axis
                when this number of points is not regular
        """
        requests = self._scan_info.setdefault("requests", {})
        assert axis_kind in set([None, "forth", "backnforth", "step"])
        meta = requests.setdefault(name, {})
        if start is not None:
            meta["start"] = start
        if stop is not None:
            meta["stop"] = stop
        if min is not None:
            meta["min"] = min
        if max is not None:
            meta["max"] = max
        if points is not None:
            meta["points"] = points
        if axis_points is not None:
            meta["axis-points"] = axis_points
        if axis_id is not None:
            assert axis_id >= 0
            meta["axis-id"] = axis_id
        if axis_kind is not None:
            meta["axis-kind"] = axis_kind
        if group is not None:
            meta["group"] = group
        if axis_points_hint is not None:
            meta["axis-points-hint"] = axis_points_hint

    @typeguard.typechecked
    def add_scatter_plot(
        self,
        name: typing.Optional[str] = None,
        x: typing.Optional[str] = None,
        y: typing.Optional[str] = None,
        value: typing.Optional[str] = None,
    ):
        """
        Add a scatter plot definition to this `scan_info`.

        This can be used as default plot for the scan.

        Arguments:
            name: Unique name for the plot. If not defined a default plot name
                is used.
            x: Channel name for the x-axis
            y: Channel name for the y-axis
            value: Channel name for the data value
        """
        plots = self._scan_info.setdefault("plots", [])
        if not isinstance(plots, list):
            raise TypeError("The 'plots' metadata is corrupted. A list is expected.")

        item = {"kind": "scatter"}
        if x is not None:
            item["x"] = x
        if y is not None:
            item["y"] = y
        if value is not None:
            item["value"] = value

        items = []
        if len(item) > 1:
            items.append(item)

        plot = {"kind": "scatter-plot", "items": items}
        if name is not None:
            plot["name"] = name

        plots.append(plot)