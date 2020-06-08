# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import typeguard
from typing import Optional

from bliss.common.utils import shorten_signature, typeguardTypeError_to_hint
from bliss.common.scans.step_by_step import timescan
from bliss.common.types import _countables, _float_or_countables, _float


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def ct(
    count_time: _float_or_countables = 1.0,
    *counter_args: _countables,
    name: str = "ct",
    title: Optional[str] = None,
    save: bool = False,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):

    """
    Counts for a specified time

    Use `ct(..., run=False)` to create a count object and
    its acquisition chain without executing the actual count.

    Note:
        This function blocks the current :class:`Greenlet`

    Args:
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'ct <count_time>']
        save (bool): save scan data to file [default: True]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    if isinstance(count_time, _countables.__args__):
        counter_args = [count_time] + list(counter_args)
        count_time = 1.0

    return timescan(
        count_time,
        *counter_args,
        npoints=1,
        name=name,
        title=title,
        scan_type="ct",
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )
