# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Most common scan procedures (:func:`~bliss.common.scans.ascan`, \
:func:`~bliss.common.scans.dscan`, :func:`~bliss.common.scans.timescan`, etc)
"""

__all__ = ["amesh", "a3mesh", "dmesh", "d3mesh"]

import logging
import types
import typeguard
from typing import Optional

from bliss.common.utils import rounder, shorten_signature, typeguardTypeError_to_hint
from bliss.common.cleanup import cleanup, axis as cleanup_axis
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.acquisition.motor import MeshStepTriggerMaster
from .scan_info import ScanInfoFactory
from .step_by_step import DEFAULT_CHAIN
from bliss.common.types import _int, _float, _scannable, _countables

_log = logging.getLogger("bliss.scans")


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def amesh(
    motor1: _scannable,
    start1: _float,
    stop1: _float,
    intervals1: _int,
    motor2: _scannable,
    start2: _float,
    stop2: _float,
    intervals2: _int,
    count_time: _float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_type: str = "amesh",
    name: str = "amesh",
    scan_info: Optional[dict] = None,
):
    """
    Mesh scan

    The amesh scan traces out a grid using motor1 and motor2. The first motor
    scans from start1 to end1 using the specified number of intervals.  The
    second motor similarly scans from start2 to end2. Each point is counted for
    for time seconds (or monitor counts).

    The scan of motor1 is done at each point scanned by motor2.  That is, the
    first motor scan is nested within the second motor scan.

    Use `amesh(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    :param backnforth if True do back and forth on the first motor
    """
    if scan_info is None:
        scan_info = dict()

    scan_info.update(
        {
            "type": scan_type,
            "save": save,
            "title": title,
            "sleep_time": sleep_time,
            "data_dim": 2,
        }
    )

    if title is None:
        args = (
            scan_type,
            motor1.name,
            rounder(motor1.tolerance, start1),
            rounder(motor1.tolerance, stop1),
            intervals1,
            motor2.name,
            rounder(motor2.tolerance, start2),
            rounder(motor2.tolerance, stop2),
            intervals2,
            count_time,
        )
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        scan_info["title"] = template.format(*args)

    npoints1 = intervals1 + 1
    npoints2 = intervals2 + 1

    scan_info.update(
        {
            "npoints1": npoints1,
            "npoints2": npoints2,
            "npoints": npoints1 * npoints2,
            "start": [start1, start2],
            "stop": [stop1, stop2],
            "count_time": count_time,
        }
    )

    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta(
        f"axis:{motor1.name}",
        start=start1,
        stop=stop1,
        points=npoints1 * npoints2,
        axis_points=npoints1,
        axis_kind="fast-backnforth" if backnforth else "fast",
    )
    factory.set_channel_meta(
        f"axis:{motor2.name}",
        start=start2,
        stop=stop2,
        points=npoints1 * npoints2,
        axis_points=npoints2,
        axis_kind="slow",
    )

    factory.add_scatter_plot(x=f"axis:{motor1.name}", y=f"axis:{motor2.name}")

    scan_params = {
        "type": scan_type,
        "npoints": npoints1 * npoints2,
        "count_time": count_time,
        "sleep_time": sleep_time,
        "start": [start1, start2],
        "stop": [stop1, stop2],
    }

    chain = DEFAULT_CHAIN.get(
        scan_params,
        counter_args,
        top_master=MeshStepTriggerMaster(
            motor1,
            start1,
            stop1,
            npoints1,
            motor2,
            start2,
            stop2,
            npoints2,
            backnforth=backnforth,
        ),
    )

    _log.info(
        "Scanning (%s, %s) from (%f, %f) to (%f, %f) in (%d, %d) points",
        motor1.name,
        motor2.name,
        start1,
        start2,
        stop1,
        stop2,
        npoints1,
        npoints2,
    )

    scan = Scan(
        chain,
        scan_info=scan_info,
        name=name,
        save=save,
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    if run:
        scan.run()

    if return_scan:
        return scan


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def dmesh(
    motor1: _scannable,
    start1: _float,
    stop1: _float,
    intervals1: _int,
    motor2: _scannable,
    start2: _float,
    stop2: _float,
    intervals2: _int,
    count_time: _float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_type: str = "dmesh",
    name: str = "dmesh",
    scan_info: Optional[dict] = None,
):
    """Relative mesh
    """
    start1 += motor1._set_position
    stop1 += motor1._set_position
    start2 += motor2._set_position
    stop2 += motor2._set_position

    scan = amesh(
        motor1,
        start1,
        stop1,
        intervals1,
        motor2,
        start2,
        stop2,
        intervals2,
        count_time,
        *counter_args,
        backnforth=backnforth,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=False,
        return_scan=True,
        scan_type=scan_type,
        name=name,
        scan_info=scan_info,
    )

    def run_with_cleanup(self, __run__=scan.run):
        with cleanup(motor1, motor2, restore_list=(cleanup_axis.POS,), verbose=True):
            __run__()

    scan.run = types.MethodType(run_with_cleanup, scan)

    if run:
        scan.run()

    if return_scan:
        return scan


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def a3mesh(
    motor1: _scannable,
    start1: _float,
    stop1: _float,
    intervals1: _int,
    motor2: _scannable,
    start2: _float,
    stop2: _float,
    intervals2: _int,
    motor3: _scannable,
    start3: _float,
    stop3: _float,
    intervals3: _int,
    count_time: _float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_type: str = "a3mesh",
    name: str = "a3mesh",
    scan_info: Optional[dict] = None,
):
    """
    Mesh scan with 3 motors

    The a3mesh scan traces out a grid using motor1, motor2 and motor3.
    Each motors uses its own specified start, stop and intervals. Each point is
    counted for time seconds (or monitor counts).

    The scan of motor1 is done at each point scanned by motor2. The scan of
    motor1+motor2 is done at each point scanned by motor3. That is, the
    first motor scan is nested within the second motor scan which is nested
    within the third motor.

    Use `a3mesh(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Arguments:
        backnforth: if True do back and forth on the first 2 motors
    """
    if scan_info is None:
        scan_info = dict()

    scan_info.update(
        {
            "type": scan_type,
            "save": save,
            "title": title,
            "sleep_time": sleep_time,
            "data_dim": 3,
        }
    )

    if title is None:
        args = (
            scan_type,
            motor1.name,
            rounder(motor1.tolerance, start1),
            rounder(motor1.tolerance, stop1),
            intervals1,
            motor2.name,
            rounder(motor2.tolerance, start2),
            rounder(motor2.tolerance, stop2),
            intervals2,
            motor3.name,
            rounder(motor3.tolerance, start3),
            rounder(motor3.tolerance, stop3),
            intervals3,
            count_time,
        )
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        scan_info["title"] = template.format(*args)

    npoints1 = intervals1 + 1
    npoints2 = intervals2 + 1
    npoints3 = intervals3 + 1
    npoints = npoints1 * npoints2 * npoints3

    scan_info.update(
        {
            "npoints1": npoints1,
            "npoints2": npoints2,
            "npoints3": npoints3,
            "npoints": npoints,
            "start": [start1, start2, start3],
            "stop": [stop1, stop2, stop3],
            "count_time": count_time,
        }
    )

    factory = ScanInfoFactory(scan_info)
    factory.set_channel_meta(
        f"axis:{motor1.name}",
        start=start1,
        stop=stop1,
        points=npoints,
        axis_points=npoints1,
        axis_kind="fast-backnforth" if backnforth else "fast",
    )
    factory.set_channel_meta(
        f"axis:{motor2.name}",
        start=start2,
        stop=stop2,
        points=npoints,
        axis_points=npoints2,
        axis_kind="slow-backnforth" if backnforth else "slow",
    )
    factory.set_channel_meta(
        f"axis:{motor3.name}",
        start=start3,
        stop=stop3,
        points=npoints,
        axis_points=npoints2,
    )

    factory.add_scatter_plot(x=f"axis:{motor1.name}", y=f"axis:{motor2.name}")

    scan_params = {
        "type": scan_type,
        "npoints": npoints,
        "count_time": count_time,
        "sleep_time": sleep_time,
        "start": [start1, start2, start3],
        "stop": [stop1, stop2, stop3],
    }

    chain = DEFAULT_CHAIN.get(
        scan_params,
        counter_args,
        top_master=MeshStepTriggerMaster(
            motor1,
            start1,
            stop1,
            npoints1,
            motor2,
            start2,
            stop2,
            npoints2,
            motor3,
            start3,
            stop3,
            npoints3,
            backnforth=backnforth,
        ),
    )

    _log.info(
        "Scanning (%s, %s, %s) from (%f, %f, %f) to (%f, %f, %f) in (%d, %d, %d) points",
        motor1.name,
        motor2.name,
        motor3.name,
        start1,
        start2,
        start3,
        stop1,
        stop2,
        stop3,
        npoints1,
        npoints2,
        npoints3,
    )

    scan = Scan(
        chain,
        scan_info=scan_info,
        name=name,
        save=save,
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    if run:
        scan.run()

    if return_scan:
        return scan


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def d3mesh(
    motor1: _scannable,
    start1: _float,
    stop1: _float,
    intervals1: _int,
    motor2: _scannable,
    start2: _float,
    stop2: _float,
    intervals2: _int,
    motor3: _scannable,
    start3: _float,
    stop3: _float,
    intervals3: _int,
    count_time: _float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_type: str = "d3mesh",
    name: str = "d3mesh",
    scan_info: Optional[dict] = None,
):
    """Relative mesh with 3 motors
    """
    start1 += motor1._set_position
    stop1 += motor1._set_position
    start2 += motor2._set_position
    stop2 += motor2._set_position
    start3 += motor3._set_position
    stop3 += motor3._set_position

    scan = a3mesh(
        motor1,
        start1,
        stop1,
        intervals1,
        motor2,
        start2,
        stop2,
        intervals2,
        motor3,
        start3,
        stop3,
        intervals3,
        count_time,
        *counter_args,
        backnforth=backnforth,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=False,
        return_scan=True,
        scan_type=scan_type,
        name=name,
        scan_info=scan_info,
    )

    def run_with_cleanup(self, __run__=scan.run):
        with cleanup(
            motor1, motor2, motor3, restore_list=(cleanup_axis.POS,), verbose=True
        ):
            __run__()

    scan.run = types.MethodType(run_with_cleanup, scan)

    if run:
        scan.run()

    if return_scan:
        return scan
