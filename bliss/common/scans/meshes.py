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

__all__ = ["anmesh", "amesh", "a3mesh", "dmesh", "d3mesh"]

import logging
import types
import typeguard
import numpy
from typing import Optional

from bliss.common.utils import rounder, shorten_signature, typeguardTypeError_to_hint
from bliss.common.cleanup import cleanup, axis as cleanup_axis
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.acquisition.motor import MeshStepTriggerMaster
from .scan_info import ScanInfoFactory
from .step_by_step import DEFAULT_CHAIN
from bliss.common.types import (
    _int,
    _float,
    _scannable,
    _countables,
    _scannable_start_stop_intervals_list,
)

_log = logging.getLogger("bliss.scans")


@typeguard.typechecked
def anmesh(
    motor_tuple_list: _scannable_start_stop_intervals_list,
    count_time: _float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_type: str = "anmesh",
    name: str = "anmesh",
    scan_info: Optional[dict] = None,
):
    """
    Mesh scan with n-motors

    This scan traces out a grid using all the motors.
    Each motors uses its own specified start, stop and intervals. Each point is
    counted for time seconds (or monitor counts).

    The first motor is the faster, and the last motor the slowest.
    And each motor is nested with the next one.

    Use `anmesh(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Arguments:
        motor_tuple_list: List of tuple (motor, start, stop, interval).
            The first motor is the fastest.
        backnforth: If True do back and forth for all the motors except the
            slowest one
    """
    assert len(motor_tuple_list) >= 2

    if scan_info is None:
        scan_info = dict()

    scan_info.update(
        {
            "type": scan_type,
            "save": save,
            "title": title,
            "sleep_time": sleep_time,
            "data_dim": len(motor_tuple_list),
        }
    )

    if title is None:
        args = []
        args.append(scan_type)
        for motor, start, stop, intervals in motor_tuple_list:
            args.append(motor.name)
            args.append(rounder(motor.tolerance, start))
            args.append(rounder(motor.tolerance, stop))
            args.append(intervals)
        args.append(count_time)
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        scan_info["title"] = template.format(*args)

    motor_list = [info[0] for info in motor_tuple_list]
    motor_name_list = [info[0].name for info in motor_tuple_list]
    start_list = [info[1] for info in motor_tuple_list]
    stop_list = [info[2] for info in motor_tuple_list]
    npoints_list = [info[3] + 1 for info in motor_tuple_list]
    sum_npoints = numpy.product(npoints_list)

    scan_info.update(
        {
            "npoints": sum_npoints,
            "start": start_list,
            "stop": stop_list,
            "count_time": count_time,
        }
    )
    for i, npoints in enumerate(npoints_list):
        scan_info[f"npoints{i+1}"] = npoints

    factory = ScanInfoFactory(scan_info)

    for i, (motor, start, stop, intervals) in enumerate(motor_tuple_list):
        kind: str
        if i == 0:
            kind = "backnforth" if backnforth else "forth"
        elif i == 1:
            kind = "backnforth" if backnforth else "forth"
        else:
            kind = "step"
        factory.set_channel_meta(
            f"axis:{motor.name}",
            start=start,
            stop=stop,
            points=sum_npoints,
            axis_id=i,
            axis_points=intervals + 1,
            axis_kind=kind,
            group="scatter",
        )

    factory.add_scatter_plot(
        x=f"axis:{motor_list[0].name}", y=f"axis:{motor_list[1].name}"
    )

    scan_params = {
        "type": scan_type,
        "npoints": sum_npoints,
        "count_time": count_time,
        "sleep_time": sleep_time,
        "start": start_list,
        "stop": stop_list,
    }

    args = []
    for motor, start, stop, intervals in motor_tuple_list:
        args.extend([motor, start, stop, intervals + 1])
    chain = DEFAULT_CHAIN.get(
        scan_params,
        counter_args,
        top_master=MeshStepTriggerMaster(*args, backnforth=backnforth),
    )

    nmotors = len(motor_tuple_list)
    template = "Scanning (%s) from (%s) to (%s) in (%s) points" % (
        ",".join(["%%s"] * nmotors),
        ",".join(["%%f"] * nmotors),
        ",".join(["%%f"] * nmotors),
        ",".join(["%%d"] * nmotors),
    )
    _log.info(template, *motor_name_list, *start_list, *stop_list, *npoints_list)

    scan = Scan(
        chain,
        scan_info=scan_info,
        name=name,
        save=save,
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    # Specify the same group for channel value
    # FIXME: Replace scan_info read by a bliss API
    for top_master, acquisition_chain in scan.scan_info["acquisition_chain"].items():
        for channel_name in acquisition_chain["scalars"]:
            factory = ScanInfoFactory(scan_info)
            factory.set_channel_meta(channel_name, group="scatter")

    if run:
        scan.run()

    if return_scan:
        return scan


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

    Argument:
        backnforth: If True do back and forth on the first motor
    """
    scan = anmesh(
        [(motor1, start1, stop1, intervals1), (motor2, start2, stop2, intervals2)],
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
    scan = anmesh(
        [
            (motor1, start1, stop1, intervals1),
            (motor2, start2, stop2, intervals2),
            (motor3, start3, stop3, intervals3),
        ],
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
