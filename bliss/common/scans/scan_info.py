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


class ScanInfoFactory:
    """
    Factory to help to feed a `scan_info` dictionary.

    Argument:
        scan_info: The scan_info to feed
    """

    def __init__(self, scan_info: typing.Dict):
        self._scan_info = scan_info

    def set_channel_meta(
        self,
        name: str,
        start: typing.Optional[float] = None,
        stop: typing.Optional[float] = None,
        min: typing.Optional[float] = None,
        max: typing.Optional[float] = None,
        points: typing.Optional[int] = None,
        axis_points: typing.Optional[int] = None,
        axis_kind: typing.Optional[str] = None,
        group: typing.Optional[str] = None,
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
                - `fast`: Fast axis for a scatter (`axis_points` have to be defined)
                - `fast-backnforth`: Fast axis for a scatter which move back and
                    forth.  (`axis_points` have to be defined)
                - `slow` Slow axis for a scatter (`axis_points` have to be defined)
            group: Specify a group for the channel. All the channels from the
                same group are supposed to contain the same amount of item at
                the end of the scan. It also can be used as a hint for
                interactive user selection.
        """
        requests = self._scan_info.setdefault("requests", {})
        assert axis_kind in set(
            [None, "slow", "fast", "fast-backnforth", "slow-backnforth", "step"]
        )
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
        if axis_kind is not None:
            if axis_points is None:
                raise ValueError(
                    "Axis kind slow/fast/fast-backnforth is regular axis, axis_points have to be defined."
                )
            meta["axis-kind"] = axis_kind
        if group is not None:
            meta["group"] = group

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
