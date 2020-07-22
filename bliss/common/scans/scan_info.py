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
                - `fast`: Fast axis for a scatter
                - `slow` Slow axis for a scatter
            group: Specify a group for the channel. All the channels from the
                same group are supposed to contain the same amount of item at
                the end of the scan. It also can be used as a hint for
                interactive user selection.
        """
        requests = self._scan_info.setdefault("requests", {})
        assert axis_kind in set([None, "slow", "fast"])
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
            meta["axis-kind"] = axis_kind
        if group is not None:
            meta["group"] = group
