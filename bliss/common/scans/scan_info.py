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
            axis_kind: Kind of axis (supported "slow" or "fast" for scatters)
        """
        requests = self._scan_info.setdefault("requests", {})
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
