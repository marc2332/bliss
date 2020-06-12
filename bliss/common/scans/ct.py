# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import typeguard
from typing import Optional
from bliss.common.deprecation import deprecated_warning

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
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    save: Optional[bool] = None,  # ignored! TO BE REMOVED IN NEAR FUTURE
    save_images: Optional[bool] = None,  # ignored! TO BE REMOVED IN NEAR FUTURE
    sleep_time: Optional[_float] = None,  # ignored! TO BE REMOVED IN NEAR FUTURE
):

    """
    Counts for a specified time. The collected data is not saved and 
    metadata is not collected.

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

    # to be removed in a futur bliss release
    if save is not None or save_images is not None:
        deprecated_warning(
            kind="function",
            name="ct",
            replacement="sct",
            reason="`ct` does no longer allow to save data",
            since_version="1.5.0",
            skip_backtrace_count=5,
            only_once=False,
        )
    if sleep_time is not None:
        deprecated_warning(
            kind="argument",
            name="sleep_time",
            reason="`ct` does no longer use sleep_time. It will be removed in near future",
            since_version="1.5.0",
            skip_backtrace_count=5,
            only_once=False,
        )
    if isinstance(count_time, _countables.__args__):
        counter_args = [count_time] + list(counter_args)
        count_time = 1.0

    s = timescan(
        count_time,
        *counter_args,
        npoints=1,
        name=name,
        title=title,
        scan_type="ct",
        save=False,
        run=False,
        return_scan=return_scan,
        scan_info=scan_info,
    )

    s._update_scan_info_with_user_scan_meta = lambda: None

    if run:
        s.run()

    return s


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def sct(
    count_time: _float_or_countables = 1.0,
    *counter_args: _countables,
    name: str = "ct",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):

    """
    like ct only that 
    Counts for a specified time. The collected data is not saved and 
    metadata is not collected.

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
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )
