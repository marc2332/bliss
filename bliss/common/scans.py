# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Most common scan procedures (:func:`~bliss.common.scans.ascan`, \
:func:`~bliss.common.scans.dscan`, :func:`~bliss.common.scans.timescan`, etc)
"""

__all__ = [
    "ascan",
    "anscan",
    "a2scan",
    "a3scan",
    "a4scan",
    "a5scan",
    "dscan",
    "dnscan",
    "d2scan",
    "d3scan",
    "d4scan",
    "d5scan",
    "amesh",
    "dmesh",
    "lineup",
    "timescan",
    "loopscan",
    "lookupscan",
    "pointscan",
    "ct",
    "DEFAULT_CHAIN",
    "cen",
    "goto_cen",
    "peak",
    "goto_peak",
    "com",
    "goto_com",
    "where",
]

import logging
import numpy
import gevent
from functools import wraps
import types

from bliss import current_session
from bliss.common.utils import rounder
from bliss.common.cleanup import cleanup, axis as cleanup_axis
from bliss.common.axis import Axis
from bliss.common.cleanup import error_cleanup
from bliss.config.settings import HashSetting
from bliss.data.scan import get_counter_names
from bliss.scanning.toolbox import DefaultAcquisitionChain
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.acquisition.motor import VariableStepTriggerMaster
from bliss.scanning.acquisition.motor import MeshStepTriggerMaster
from bliss.controllers.motor import CalcController

_log = logging.getLogger("bliss.scans")

DEFAULT_CHAIN = DefaultAcquisitionChain()


def ascan(motor, start, stop, intervals, count_time, *counter_args, **kwargs):
    """
    Absolute scan

    Scans one motor, as specified by *motor*. The motor starts at the position
    given by *start* and ends at the position given by *stop*. The step size is
    `(*start*-*stop*)/(*npoints*-1)`. The number of intervals will be
    *npoints*-1. Count time is given by *count_time* (seconds).

    Use `ascan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        motor (Axis): motor to scan
        start (float): motor start position
        stop (float): motor end position
        intervals (int): the number of intervals
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'ascan <motor> ... <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool or None): save image files [default: None, means it follows 'save']
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    args = [motor, start, stop]
    args += counter_args
    return anscan(count_time, intervals, *args, **kwargs)


def dscan(motor, start, stop, intervals, count_time, *counter_args, **kwargs):
    """
    Relative scan

    Scans one motor, as specified by *motor*. If the motor is at position *X*
    before the scan begins, the scan will run from `X+start` to `X+end`.
    The step size is `(*start*-*stop*)/(*npoints*-1)`. The number of intervals
    will be *npoints*-1. Count time is given by *count_time* (seconds).

    At the end of the scan (even in case of error) the motor will return to
    its initial position

    Use `dscan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        motor (Axis): motor to scan
        start (float): motor relative start position
        stop (float): motor relative end position
        intervals (int): the number of intervals
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'dscan <motor> ... <count_time>']
        save (bool): save scan data to file [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    args = [motor, start, stop]
    args += counter_args
    return dnscan(count_time, intervals, *args, **kwargs)


def lineup(motor, start, stop, intervals, count_time, *counter_args, **kwargs):
    if len(counter_args) == 0:
        raise ValueError("lineup: please specify a counter")
    if len(counter_args) > 1:
        raise ValueError("lineup: too many counters")

    kwargs["type"] = "lineup"
    kwargs["name"] = kwargs.get("name", "lineup")
    kwargs["return_scan"] = True
    scan = dscan(motor, start, stop, intervals, count_time, counter_args[0], **kwargs)
    scan.goto_peak(counter_args[0])
    return scan


def amesh(
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
    **kwargs,
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
    if not isinstance(intervals1, int):
        raise ValueError("number of intervals for motor1 must be an integer number.")
    if not isinstance(intervals2, int):
        raise ValueError("number of intervals for motor2 must be an integer number.")

    save_images = kwargs.pop("save_images", None)

    scan_info = {
        "type": kwargs.get("type", "amesh"),
        "save": kwargs.get("save", True),
        "title": kwargs.get("title"),
        "sleep_time": kwargs.get("sleep_time"),
        "data_dim": 2,
    }

    if scan_info["title"] is None:
        args = (
            scan_info["type"],
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

    backnforth = kwargs.pop("backnforth", False)
    chain = DEFAULT_CHAIN.get(
        scan_info,
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
        name=kwargs.setdefault("name", "amesh"),
        save=scan_info["save"],
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    if kwargs.get("run", True):
        scan.run()

    if kwargs.get("return_scan", True):
        return scan


def dmesh(
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
    **kwargs,
):
    """Relative amesh
    """
    if not isinstance(intervals1, int):
        raise ValueError("number of intervals for motor1 must be an integer number.")
    if not isinstance(intervals2, int):
        raise ValueError("number of intervals for motor2 must be an integer number.")

    kwargs.setdefault("type", "dmesh")
    kwargs.setdefault("name", "dmesh")
    run = kwargs.pop("run", True)
    kwargs["run"] = False

    start1 += motor1.position
    stop1 += motor1.position
    start2 += motor2.position
    stop2 += motor2.position

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
        **kwargs,
    )

    def run_with_cleanup(self, __run__=scan.run):
        with cleanup(motor1, motor2, restore_list=(cleanup_axis.POS,), verbose=True):
            __run__()

    scan.run = types.MethodType(run_with_cleanup, scan)

    if run:
        scan.run()

    return scan


def a2scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Absolute 2 motors scan

    Scans two motors, as specified by *motor1* and *motor2*. The motors start
    at the positions given by *start1* and *start2* and end at the positions
    given by *stop1* and *stop2*. The step size for each motor is given by
    `(*start*-*stop*)/(*intervals)`. Count time is given by *count_time* (seconds).

    Use `a2scan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        motor1 (Axis): motor1 to scan
        start1 (float): motor1 start position
        stop1 (float): motor1 end position
        motor2 (Axis): motor2 to scan
        start2 (float): motor2 start position
        stop2 (float): motor2 end position
        intervals (int): the number of intervals
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'a2scan <motor1> ... <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool or None): save image files [default: None, means it follows 'save']
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    args = [motor1, start1, stop1, motor2, start2, stop2]
    args += counter_args
    return anscan(count_time, intervals, *args, **kwargs)


def lookupscan(count_time, *motors_positions, **kwargs):
    """Lookupscan usage:
    lookupscan(0.1,m0,numpy.arange(0,2,0.5),m1,numpy.linspace(1,3,4),diode2)
    to scan 2 motor with their own position table and with diode2 as
    the only counter.
    """
    counter_list = list()
    tmp_l, motors_positions = list(motors_positions), list()
    starts_list = list()
    stops_list = list()
    while tmp_l:
        val = tmp_l.pop(0)
        if isinstance(val, Axis):
            pos = tmp_l.pop(0)
            starts_list.append(pos[0])
            stops_list.append(pos[-1])
            motors_positions.extend((val, pos))
        else:
            counter_list.append(val)

    kwargs.setdefault(
        "title",
        "lookupscan %f on motors (%s)"
        % (count_time, ",".join(x.name for x in motors_positions[::2])),
    )

    scan_info = {
        "npoints": len(motors_positions[1]),
        "count_time": count_time,
        "type": kwargs.get("type", "lookupscan"),
        "save": kwargs.get("save", True),
        "start": starts_list,  # kwargs.get("start", []),
        "stop": stops_list,  # kwargs.get("stop", []),
        "title": kwargs["title"],
        "sleep_time": kwargs.get("sleep_time"),
    }

    chain = DEFAULT_CHAIN.get(
        scan_info, counter_list, top_master=VariableStepTriggerMaster(*motors_positions)
    )
    scan = Scan(
        chain,
        scan_info=scan_info,
        name=kwargs.setdefault("name", "lookupscan"),
        save=scan_info["save"],
        save_images=kwargs.get("save_images"),
        data_watch_callback=StepScanDataWatch(),
    )

    if kwargs.get("run", True):
        scan.run()
    return scan


def anscan(count_time, intervals, *motors_positions, **kwargs):
    """
    anscan usage:
      anscan(ctime, intervals, m1, start_m1_pos, stop_m1_pos, m2, start_m2_pos, stop_m2_pos, counter)
    10 points scan at 0.1 second integration on motor **m1** from
    *stop_m1_pos* to *stop_m1_pos* and **m2** from *start_m2_pos* to
    *stop_m2_pos* and with one counter.

    example:
      anscan(0.1, 10, m1, 1, 2, m2, 3, 7, diode2)
    10 points scan at 0.1 second integration on motor **m1** from
    1 to 2 and **m2** from 3 to 7 and with diode2 as the only counter.
    """

    if not isinstance(intervals, int):
        raise ValueError("number of interval must be an integer number.")
    npoints = intervals + 1
    counter_list = list()
    # scan type is forced to be either aNscan or dNscan
    scan_type = kwargs.pop("type", None)
    tmp_l, motors_positions = list(motors_positions), list()
    title_list = list()
    starts_list = []
    stops_list = []
    while tmp_l:
        val = tmp_l.pop(0)
        if isinstance(val, Axis):
            start = tmp_l.pop(0)
            starts_list.append(start)
            stop = tmp_l.pop(0)
            stops_list.append(stop)
            d = val.position if scan_type == "dscan" else 0
            title_list.extend(
                (
                    val.name,
                    rounder(val.tolerance, start - d),
                    rounder(val.tolerance, stop - d),
                )
            )
            motors_positions.extend((val, numpy.linspace(start, stop, npoints)))
        else:
            counter_list.append(val)

    kwargs.setdefault("start", starts_list)
    kwargs.setdefault("stop", stops_list)

    if scan_type == "dscan":
        scan_type = (
            f"d{len(title_list)//3}scan" if len(title_list) // 3 > 1 else "dscan"
        )
    else:
        scan_type = (
            f"a{len(title_list)//3}scan" if len(title_list) // 3 > 1 else "ascan"
        )
    kwargs["type"] = scan_type

    kwargs.setdefault("name", scan_type)
    if "title" not in kwargs:
        args = [scan_type]
        args += title_list
        args += [intervals, count_time]
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        kwargs["title"] = template.format(*args)

    motors_positions += counter_list
    return lookupscan(count_time, *motors_positions, **kwargs)


def dnscan(count_time, intervals, *motors_positions, **kwargs):
    """
    dnscan usage:
      dnscan(0.1, 10, m0, rel_start_m0, rel_end_m0, m1, rel_start_m1, rel_stop_m1, counter)
    example:
      dnscan(0.1, 10, m0, -1, 1, m1, -2, 2, diode2)
    """

    if not isinstance(intervals, int):
        raise ValueError("number of interval must be an integer number.")
    counter_list = list()
    tmp_l, motors_positions = list(motors_positions), list()

    starts_list = []  # absolute start values.
    stops_list = []  # absolute stop values.
    old_pos_list = []  # absolute original motor positions.
    motors_list = []

    while tmp_l:
        val = tmp_l.pop(0)
        if isinstance(val, Axis):
            motors_list.append(val)
            oldpos = val.position
            old_pos_list.append(oldpos)
            start = tmp_l.pop(0)
            starts_list.append(start)
            stop = tmp_l.pop(0)
            stops_list.append(stop)
            motors_positions.extend((val, oldpos + start, oldpos + stop))
        else:
            counter_list.append(val)

    run = kwargs.pop("run", True)
    kwargs["run"] = False
    kwargs["type"] = "dscan"
    kwargs.setdefault("start", starts_list)
    kwargs.setdefault("stop", stops_list)

    motors_positions += counter_list

    scan = anscan(count_time, intervals, *motors_positions, **kwargs)

    def run_with_cleanup(self, __run__=scan.run):
        with cleanup(*motors_list, restore_list=(cleanup_axis.POS,), verbose=True):
            __run__()

    scan.run = types.MethodType(run_with_cleanup, scan)

    if run:
        scan.run()

    return scan


def a3scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    motor3,
    start3,
    stop3,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Absolute 3 motors scan.
    Identical to a2scan but for 3 motors.
    """
    args = [motor1, start1, stop1, motor2, start2, stop2, motor3, start3, stop3]
    args += counter_args
    return anscan(count_time, intervals, *args, **kwargs)


def a4scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    motor3,
    start3,
    stop3,
    motor4,
    start4,
    stop4,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Absolute 4 motors scan.
    Identic to a2scan but for 4 motors.
    """
    args = [
        motor1,
        start1,
        stop1,
        motor2,
        start2,
        stop2,
        motor3,
        start3,
        stop3,
        motor4,
        start4,
        stop4,
    ]
    args += counter_args
    return anscan(count_time, intervals, *args, **kwargs)


def a5scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    motor3,
    start3,
    stop3,
    motor4,
    start4,
    stop4,
    motor5,
    start5,
    stop5,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Absolute 5 motors scan.
    Identic to a2scan but for 5 motors.
    """
    args = [
        motor1,
        start1,
        stop1,
        motor2,
        start2,
        stop2,
        motor3,
        start3,
        stop3,
        motor4,
        start4,
        stop4,
        motor5,
        start5,
        stop5,
    ]
    args += counter_args
    return anscan(count_time, intervals, *args, **kwargs)


def d3scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    motor3,
    start3,
    stop3,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Relative 3 motors scan.
    Identic to d2scan but for 3 motors.
    """
    args = [motor1, start1, stop1, motor2, start2, stop2, motor3, start3, stop3]
    args += counter_args
    return dnscan(count_time, intervals, *args, **kwargs)


def d4scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    motor3,
    start3,
    stop3,
    motor4,
    start4,
    stop4,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Relative 4 motors scan.
    Identic to d2scan but for 4 motors.
    """
    args = [
        motor1,
        start1,
        stop1,
        motor2,
        start2,
        stop2,
        motor3,
        start3,
        stop3,
        motor4,
        start4,
        stop4,
    ]
    args += counter_args
    return dnscan(count_time, intervals, *args, **kwargs)


def d5scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    motor3,
    start3,
    stop3,
    motor4,
    start4,
    stop4,
    motor5,
    start5,
    stop5,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Relative 5 motors scan.
    Identic to d2scan but for 5 motors.
    """
    args = [
        motor1,
        start1,
        stop1,
        motor2,
        start2,
        stop2,
        motor3,
        start3,
        stop3,
        motor4,
        start4,
        stop4,
        motor5,
        start5,
        stop5,
    ]
    args += counter_args
    return dnscan(count_time, intervals, *args, **kwargs)


def d2scan(
    motor1,
    start1,
    stop1,
    motor2,
    start2,
    stop2,
    intervals,
    count_time,
    *counter_args,
    **kwargs,
):
    """
    Relative 2 motors scan

    Scans two motors, as specified by *motor1* and *motor2*. Each motor moves
    the same number of points. If a motor is at position *X*
    before the scan begins, the scan will run from `X+start` to `X+end`.
    The step size of a motor is `(*start*-*stop*)/(*intervals*)`.
    Count time is given by *count_time*
    (seconds).

    At the end of the scan (even in case of error) the motors will return to
    their initial positions.

    Use `d2scan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        motor1 (Axis): motor1 to scan
        start1 (float): motor1 relative start position
        stop1 (float): motor1 relative end position
        motor2 (Axis): motor2 to scan
        start2 (float): motor2 relative start position
        stop2 (float): motor2 relative end position
        intervals (int): the number of intervals
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'd2scan <motor1> ... <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool or None): save image files [default: None, means it follows 'save']
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    args = [motor1, start1, stop1, motor2, start2, stop2]
    args += counter_args
    return dnscan(count_time, intervals, *args, **kwargs)


def timescan(count_time, *counter_args, **kwargs):
    """
    Time scan

    Use `timescan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'timescan <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool or None): save image files [default: None, means it follows 'save']
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
        npoints (int): number of points [default: 0, meaning infinite number of points]
        output_mode (str): valid are 'tail' (append each line to output) or
                           'monitor' (refresh output in single line)
                           [default: 'tail']
    """
    save_images = kwargs.get("save_images")

    scan_info = {
        "type": kwargs.get("type", "timescan"),
        "save": kwargs.get("save", True),
        "title": kwargs.get("title"),
        "sleep_time": kwargs.get("sleep_time"),
        "output_mode": kwargs.get("output_mode", "tail"),
    }

    if scan_info["title"] is None:
        args = scan_info["type"], count_time
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        scan_info["title"] = template.format(*args)

    npoints = kwargs.get("npoints", 0)

    scan_info.update(
        {"npoints": npoints, "start": [], "stop": [], "count_time": count_time}
    )

    _log.info("Doing %s", scan_info["type"])

    chain = DEFAULT_CHAIN.get(scan_info, counter_args)

    scan = Scan(
        chain,
        scan_info=scan_info,
        name=kwargs.setdefault("name", "timescan"),
        save=scan_info["save"],
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    if kwargs.get("run", True):
        scan.run()

    if kwargs.get("return_scan", True):
        return scan


def loopscan(npoints, count_time, *counter_args, **kwargs):
    """
    Similar to :ref:`timescan` but npoints is mandatory

    Use `loopscan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        npoints (int): number of points
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'timescan <count_time>']
        save (bool): save scan data to file [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
        output_mode (str): valid are 'tail' (append each line to output) or
                           'monitor' (refresh output in single line)
                           [default: 'tail']
    """
    if not isinstance(npoints, int):
        raise ValueError("number of point must be an integer number.")
    kwargs.setdefault("npoints", npoints)
    kwargs.setdefault("name", "loopscan")
    kwargs.setdefault("type", "loopscan")
    args = kwargs.get("type", "loopscan"), npoints, count_time
    template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
    title = template.format(*args)
    kwargs.setdefault("title", title)
    return timescan(count_time, *counter_args, **kwargs)


def ct(count_time, *counter_args, **kwargs):
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
    kwargs["type"] = "ct"
    kwargs.setdefault("save", False)
    kwargs["npoints"] = 1

    kwargs.setdefault("name", "ct")

    return timescan(count_time, *counter_args, **kwargs)


def pointscan(motor, positions, count_time, *counter_args, **kwargs):
    """
    Point scan

    Scans one motor, as specified by *motor*. The motor starts at the
    position given by the first value in *positions* and ends at the
    position given by last value *positions*.  Count time is given by
    *count_time* (seconds).

    Args:
        motor (Axis): motor to scan
        positions (list): a list of positions
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'pointscan <motor> <positions>']
        save (bool): save scan data to file [default: True]
        save_images (bool or None): save image files [default: None, means it follows 'save']
        return_scan (bool): True by default
    """
    save_images = kwargs.pop("save_images", None)

    scan_info = {
        "type": kwargs.get("type", "pointscan"),
        "save": kwargs.get("save", True),
        "title": kwargs.get("title"),
    }

    npoints = len(positions)
    if scan_info["title"] is None:
        args = (
            scan_info["type"],
            motor.name,
            positions[0],
            positions[npoints - 1],
            npoints,
            count_time,
        )
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        scan_info["title"] = template.format(*args)

    scan_info.update(
        {
            "npoints": npoints,
            "total_acq_time": npoints * count_time,
            "start": positions[0],
            "stop": positions[npoints - 1],
            "count_time": count_time,
        }
    )

    chain = DEFAULT_CHAIN.get(
        scan_info, counter_args, top_master=VariableStepTriggerMaster(motor, positions)
    )

    _log.info(
        "Scanning %s from %f to %f in %d points",
        motor.name,
        positions[0],
        positions[npoints - 1],
        npoints,
    )

    scan = Scan(
        chain,
        scan_info=scan_info,
        name=kwargs.setdefault("name", "pointscan"),
        save=scan_info["save"],
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    scan.run()
    if kwargs.get("return_scan", True):
        return scan


# Alignment Helpers
def _get_selected_counter_name(counter=None):
    """
    Returns the name of the counter selected *in flint*.

    Returns ONLY ONE counter.

    Raises RuntimeError if more than one counter is selected.

    Used to determine which counter to use for cen pic curs functions.
    """
    if not current_session.scans:
        raise RuntimeError("Scans list is empty!")
    scan_counter_names = set(get_counter_names(current_session.scans[-1]))
    plot_select = HashSetting("%s:plot_select" % current_session.name)
    selected_flint_counter_names = set(plot_select.keys())
    alignment_counts = scan_counter_names.intersection(selected_flint_counter_names)
    if not alignment_counts:
        raise RuntimeError(
            "No counter selected...\n"
            "Hints: Use flint or plotselect to define which counter to use for alignment"
        )
    elif len(alignment_counts) > 1:
        if counter is None:
            raise RuntimeError(
                "There is actually several counter selected (%s).\n"
                "Only one should be selected.\n"
                "Hints: Use flint or plotselect to define which counter to use for alignment"
                % alignment_counts
            )
        if counter.name in alignment_counts:
            return counter.name
        else:
            raise RuntimeError(
                f"Counter {counter.name} is not part of the last scan.\n"
            )

    return alignment_counts.pop()


def last_scan_motor(axis=None):
    """
    Return the last motor used in the last scan
    """
    if not len(current_session.scans):
        raise RuntimeError("No scan available. Hint: do at least one ;)")
    scan = current_session.scans[-1]
    axis_name = scan._get_data_axis_name(axis=axis)
    return current_session.env_dict[axis_name]


def last_scan_motors():
    """
    Return a list of motor used in the last scan
    """
    if not len(current_session.scans):
        raise RuntimeError("No scan available. Hint: do at least one ;)")
    scan = current_session.scans[-1]
    axes_name = scan._get_data_axes_name()
    return [current_session.env_dict[axis_name] for axis_name in axes_name]


def plotselect(*counters):
    """
    Select counter(s) to use for:
    * alignment (bliss/common/scans.py:_get_selected_counter_name())
    * flint display (bliss/flint/plot1d.py)
    Saved as a HashSetting with '<session_name>:plot_select' key.
    """
    plot_select = HashSetting("%s:plot_select" % current_session.name)
    counter_names = dict()
    for cnt in counters:
        fullname = cnt.fullname  # should be like: <controller.counter>
        counter_names[fullname] = "Y1"
    plot_select.set(counter_names)


def get_plotted_counters():
    """
    Returns names of plotted counters as a list (get list from a HashSetting
    with '<session_name>:plot_select' key).
    """
    plot_select = HashSetting("%s:plot_select" % current_session.name)

    plotted_cnt_list = list()

    for cnt_name in plot_select.get_all():
        plotted_cnt_list.append(cnt_name.split(":")[1])

    return plotted_cnt_list


def _remove_real_dependent_of_calc(motors):
    """
    remove real motors if depend of a calc axis
    """
    realmot = set()
    for mot in motors:
        ctrl = mot.controller
        if isinstance(ctrl, CalcController):
            realmot.update(ctrl.reals)
    return set(motors) - realmot


def _multimotors(func):
    @wraps(func)
    def f(counter=None, axis=None):
        try:
            return func(counter=counter, axis=axis)
        except ValueError:
            if axis is not None:
                raise
            motors = last_scan_motors()
            if len(motors) <= 1:
                raise
            # check if there is some calcaxis with associated real
            motors = _remove_real_dependent_of_calc(motors)
            if len(motors) == 1:
                return func(counter=counter, axis=motors.pop())
            return {mot: func(counter=counter, axis=mot) for mot in motors}

    return f


def _goto_multimotors(func):
    @wraps(func)
    def f(counter=None, axis=None):
        try:
            return func(counter=counter, axis=axis)
        except ValueError:
            if axis is not None:
                raise
            motors = last_scan_motors()
            if len(motors) <= 1:
                raise
            motors = _remove_real_dependent_of_calc(motors)
            if len(motors) == 1:
                return func(counter=counter, axis=motors.pop())

            with error_cleanup(*motors, restore_list=(cleanup_axis.POS,), verbose=True):
                tasks = [
                    gevent.spawn(func, counter=counter, axis=mot) for mot in motors
                ]
                try:
                    gevent.joinall(tasks, raise_error=True)
                finally:
                    gevent.killall(tasks)

    return f


@_multimotors
def cen(counter=None, axis=None):
    counter_name = _get_selected_counter_name(counter=counter)
    return current_session.scans[-1].cen(counter_name, axis=axis)


@_goto_multimotors
def goto_cen(counter=None, axis=None):
    counter_name = _get_selected_counter_name(counter=counter)
    motor = last_scan_motor(axis)
    scan = current_session.scans[-1]
    motor = last_scan_motor(axis)
    cfwhm, _ = scan.cen(counter_name, axis=axis)
    _log.warning("Motor %s will move from %f to %f", motor.name, motor.position, cfwhm)
    return scan.goto_cen(counter_name, axis=axis)


@_multimotors
def com(counter=None, axis=None):
    counter_name = _get_selected_counter_name(counter=counter)
    return current_session.scans[-1].com(counter_name, axis=axis)


@_goto_multimotors
def goto_com(counter=None, axis=None):
    counter_name = _get_selected_counter_name(counter=counter)
    motor = last_scan_motor(axis)
    scan = current_session.scans[-1]
    motor = last_scan_motor(axis)
    com_pos = scan.com(counter_name, axis=axis)
    _log.warning(
        "Motor %s will move from %f to %f", motor.name, motor.position, com_pos
    )
    return current_session.scans[-1].goto_com(counter_name, axis=axis)


@_multimotors
def peak(counter=None, axis=None):
    counter_name = _get_selected_counter_name(counter=counter)
    return current_session.scans[-1].peak(counter_name, axis=axis)


@_goto_multimotors
def goto_peak(counter=None, axis=None):
    counter_name = _get_selected_counter_name(counter=counter)
    motor = last_scan_motor(axis)
    scan = current_session.scans[-1]
    motor = last_scan_motor(axis=axis)
    peak_pos = scan.peak(counter_name, axis=axis)
    _log.warning(
        "Motor %s will move from %f to %f", motor.name, motor.position, peak_pos
    )
    return scan.goto_peak(counter_name, axis=axis)


def where():
    for axis in last_scan_motors():
        current_session.scans[-1].where(axis=axis)
