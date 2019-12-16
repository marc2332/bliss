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
import typeguard
from typing import Union, Optional, Tuple, List, Sequence

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
from bliss.common.counter import Counter
from bliss.common.measurementgroup import MeasurementGroup
from bliss.common.protocols import CounterContainer, Scannable

_log = logging.getLogger("bliss.scans")

DEFAULT_CHAIN = DefaultAcquisitionChain()

_countable = Counter
_countables = Union[Counter, MeasurementGroup, CounterContainer, Tuple]
_scannable = Scannable
_scannable_start_stop_list = List[Tuple[_scannable, float, float]]
_position_list = Union[Sequence, numpy.ndarray]
_scannable_position_list = List[Tuple[_scannable, _position_list]]


@typeguard.typechecked
def ascan(
    motor: _scannable,
    start: float,
    stop: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
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
    return anscan(
        [(motor, start, stop)],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def dscan(
    motor: _scannable,
    start: float,
    stop: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
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
    return dnscan(
        [(motor, start, stop)],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def lineup(
    motor: _scannable,
    start: float,
    stop: float,
    intervals: int,
    count_time: float,
    counter: _countable,
    name: str = "lineup",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
):

    # ~ if len(counter_args) == 0:
    # ~ raise ValueError("lineup: please specify a counter")
    # ~ if len(counter_args) > 1:
    # ~ raise ValueError("lineup: too many counters")

    scan = dscan(
        motor,
        start,
        stop,
        intervals,
        count_time,
        counter,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=True,
    )
    scan.goto_peak(counter)

    if return_scan:
        return scan


@typeguard.typechecked
def amesh(
    motor1: _scannable,
    start1: float,
    stop1: float,
    intervals1: int,
    motor2: _scannable,
    start2: float,
    stop2: float,
    intervals2: int,
    count_time: float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
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

    requests = {}
    requests[f"axis:{motor1.name}"] = {
        "start": start1,
        "stop": stop1,
        "points": npoints1 * npoints2,
        "axes-points": npoints1,
        "axes-kind": "fast",
    }
    requests[f"axis:{motor2.name}"] = {
        "start": start2,
        "stop": stop2,
        "points": npoints1 * npoints2,
        "axes-points": npoints2,
        "axes-kind": "slow",
    }
    scan_info["requests"] = requests

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


@typeguard.typechecked
def dmesh(
    motor1: _scannable,
    start1: float,
    stop1: float,
    intervals1: int,
    motor2: _scannable,
    start2: float,
    stop2: float,
    intervals2: int,
    count_time: float,
    *counter_args: _countables,
    backnforth: bool = False,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_type: str = "dmesh",
    name: str = "dmesh",
    scan_info: Optional[dict] = None,
):
    """Relative mesh
    """
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


@typeguard.typechecked
def a2scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
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
    return anscan(
        [(motor1, start1, stop1), (motor2, start2, stop2)],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


# TODO: What is the difference between type and name (keep in mind that there is also title)
@typeguard.typechecked
def lookupscan(
    motor_pos_tuple_list: _scannable_position_list,
    count_time,
    *counter_args: _countables,
    scan_type: str = "lookupscan",
    name: str = "lookupscan",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,
):
    """Lookupscan usage:
    lookupscan([(m0,numpy.arange(0,2,0.5)),(m1,numpy.linspace(1,3,4))],0.1,diode2)
    to scan 2 motor with their own position table and with diode2 as
    the only counter.
    
    arguments:
    motor_pos_tuple_list: a list of tuples of the following type (motor,positions). Positions can be provided as numpy array, list or tuple
    count_time: count time in seconds
    *counter_args: as many counter-providing objects as used in the scan (seperated by comma)
    
    keyword arguments:
    scan_type: str = "lookupscan",
    name: str = "lookupscan",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,
    """
    if scan_info is None:
        scan_info = dict()
    if scan_params is None:
        scan_params = dict()

    npoints = len(motor_pos_tuple_list[0][1])
    motors_positions = list()
    title_list = list()

    for m_tup in motor_pos_tuple_list:
        assert len(m_tup[1]) == npoints
        motors_positions.extend((m_tup[0], m_tup[1]))

    if not title:
        title = "lookupscan %f on motors (%s)" % (
            count_time,
            ",".join(x[0].name for x in motor_pos_tuple_list),
        )

    scan_info.update(
        {
            "npoints": npoints,
            "count_time": count_time,
            "type": scan_type,
            "save": save,
            "title": title,
            "sleep_time": sleep_time,
        }
    )

    scan_params.update(
        {
            "npoints": npoints,
            "count_time": count_time,
            "sleep_time": sleep_time,
            "type": scan_type,
        }
    )

    chain = DEFAULT_CHAIN.get(
        scan_params,
        counter_args,
        top_master=VariableStepTriggerMaster(*motors_positions),
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


# TODO: what is the difference between type and name?
# TODO: type is really an ugly key-word-arg
# TODO: what is the option return_scan good for?
@typeguard.typechecked
def anscan(
    motor_tuple_list: _scannable_start_stop_list,
    count_time: float,
    intervals: int,
    *counter_args: _countables,
    scan_type: Optional[str] = None,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    anscan usage:
      anscan( [(m1, start_m1_pos, stop_m1_pos), (m2, start_m2_pos, stop_m2_pos)], ctime, intervals, counter)
    10 points scan at 0.1 second integration on motor **m1** from
    *stop_m1_pos* to *stop_m1_pos* and **m2** from *start_m2_pos* to
    *stop_m2_pos* and with one counter.
    
    arguments:
    motor_tuple_list: a list of tuples of the following type (motor,start,stop)
    count_time: count time in seconds
    intervals: number of intervals
    *counter_args: as many counter-providing objects as used in the scan (seperated by comma)
    
    keyword arguments:
    scan_type: str = "lookupscan",
    name: str = "lookupscan",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,

    example:
      anscan( [(m1, 1, 2), (m2, 3, 7)], 0.1, 10, diode2)
    10 points scan at 0.1 second integration on motor **m1** from
    1 to 2 and **m2** from 3 to 7 and with diode2 as the only counter.
    """

    npoints = intervals + 1
    if scan_info is None:
        scan_info = dict()
    motors_positions = list()
    title_list = list()
    starts_list = list()
    stops_list = list()
    for m_tup in motor_tuple_list:
        mot = m_tup[0]
        d = mot.position if scan_type == "dscan" else 0
        start = m_tup[1]
        stop = m_tup[2]
        title_list.extend(
            (mot.name, rounder(mot.tolerance, start), rounder(mot.tolerance, stop))
        )
        start = m_tup[1] + d
        stop = m_tup[2] + d
        motors_positions.append((mot, numpy.linspace(start, stop, npoints)))
        starts_list.append(start)
        stops_list.append(stop)

    scan_info["start"] = starts_list
    scan_info["stop"] = stops_list

    scan_params = dict()
    scan_params["start"] = starts_list
    scan_params["stop"] = stops_list

    # scan type is forced to be either aNscan or dNscan
    if scan_type == "dscan":
        scan_type = (
            f"d{len(title_list)//3}scan" if len(title_list) // 3 > 1 else "dscan"
        )
    else:
        scan_type = (
            f"a{len(title_list)//3}scan" if len(title_list) // 3 > 1 else "ascan"
        )

    if not name:
        name = scan_type

    if not title:
        args = [scan_type]
        args += title_list
        args += [intervals, count_time]
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        title = template.format(*args)

    return lookupscan(
        motors_positions,
        count_time,
        *counter_args,
        save=save,
        save_images=save_images,
        run=run,
        title=title,
        name=name,
        scan_type=scan_type,
        sleep_time=sleep_time,
        return_scan=return_scan,
        scan_info=scan_info,
        scan_params=scan_params,
    )


@typeguard.typechecked
def dnscan(
    motor_tuple_list: _scannable_start_stop_list,
    count_time: float,
    intervals: int,
    *counter_args: _countables,
    scan_type: Optional[str] = None,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    dnscan usage:
      dnscan([(m0, rel_start_m0, rel_end_m0), (m1, rel_start_m1, rel_stop_m1)], 0.1, 10, counter)
    
    arguments:
    motor_tuple_list: a list of tuples of the following type (motor,start,stop) start and stop are relative positions
    count_time: count time in seconds
    intervals: number of intervals
    *counter_args: as many counter-providing objects as used in the scan (seperated by comma)
    
    keyword arguments:
    scan_type: str = "lookupscan",
    name: str = "lookupscan",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,

    
    example:
      dnscan([(m0, -1, 1),(m1, -2, 2)],0.1, 10, diode2)
    """

    scan = anscan(
        motor_tuple_list,
        count_time,
        intervals,
        *counter_args,
        save=save,
        save_images=save_images,
        title=title,
        name=name,
        scan_type="dscan",
        sleep_time=sleep_time,
        run=False,
        scan_info=scan_info,
    )

    def run_with_cleanup(self, __run__=scan.run):
        with cleanup(
            *[m[0] for m in motor_tuple_list],
            restore_list=(cleanup_axis.POS,),
            verbose=True,
        ):
            __run__()

    scan.run = types.MethodType(run_with_cleanup, scan)

    if run:
        scan.run()

    if return_scan:
        return scan


@typeguard.typechecked
def a3scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    motor3: _scannable,
    start3: float,
    stop3: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Absolute 3 motors scan.
    Identical to a2scan but for 3 motors.
    """
    return anscan(
        [(motor1, start1, stop1), (motor2, start2, stop2), (motor3, start3, stop3)],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def a4scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    motor3: _scannable,
    start3: float,
    stop3: float,
    motor4: _scannable,
    start4: float,
    stop4: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Absolute 4 motors scan.
    Identic to a2scan but for 4 motors.
    """

    return anscan(
        [
            (motor1, start1, stop1),
            (motor2, start2, stop2),
            (motor3, start3, stop3),
            (motor4, start4, stop4),
        ],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def a5scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    motor3: _scannable,
    start3: float,
    stop3: float,
    motor4: _scannable,
    start4: float,
    stop4: float,
    motor5: _scannable,
    start5: float,
    stop5: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Absolute 5 motors scan.
    Identic to a2scan but for 5 motors.
    """
    return anscan(
        [
            (motor1, start1, stop1),
            (motor2, start2, stop2),
            (motor3, start3, stop3),
            (motor4, start4, stop4),
            (motor5, start5, stop5),
        ],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def d3scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    motor3: _scannable,
    start3: float,
    stop3: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Relative 3 motors scan.
    Identic to d2scan but for 3 motors.
    """
    return dnscan(
        [(motor1, start1, stop1), (motor2, start2, stop2), (motor3, start3, stop3)],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def d4scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    motor3: _scannable,
    start3: float,
    stop3: float,
    motor4: _scannable,
    start4: float,
    stop4: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Relative 4 motors scan.
    Identic to d2scan but for 4 motors.
    """
    return dnscan(
        [
            (motor1, start1, stop1),
            (motor2, start2, stop2),
            (motor3, start3, stop3),
            (motor4, start4, stop4),
        ],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def d5scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    motor3: _scannable,
    start3: float,
    stop3: float,
    motor4: _scannable,
    start4: float,
    stop4: float,
    motor5: _scannable,
    start5: float,
    stop5: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Relative 5 motors scan.
    Identic to s2scan but for 5 motors.
    """
    return dnscan(
        [
            (motor1, start1, stop1),
            (motor2, start2, stop2),
            (motor3, start3, stop3),
            (motor4, start4, stop4),
            (motor5, start5, stop5),
        ],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def d2scan(
    motor1: _scannable,
    start1: float,
    stop1: float,
    motor2: _scannable,
    start2: float,
    stop2: float,
    intervals: int,
    count_time: float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
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
    return dnscan(
        [(motor1, start1, stop1), (motor2, start2, stop2)],
        count_time,
        intervals,
        *counter_args,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def timescan(
    count_time: float,
    *counter_args: _countables,
    npoints: Optional[int] = 0,
    name: str = "timescan",
    title: Optional[str] = None,
    scan_type: str = "timescan",
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
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
    """
    #        output_mode (str): valid are 'tail' (append each line to output) or
    #                           'monitor' (refresh output in single line)
    #                           [default: 'tail']

    if scan_info is None:
        scan_info = dict()

    scan_info.update(
        {
            "type": scan_type,
            "save": save,
            "sleep_time": sleep_time,
            #       "output_mode": kwargs.get("output_mode", "tail"),
        }
    )

    if title is None:
        args = scan_type, count_time
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        scan_info["title"] = template.format(*args)

    scan_info.update({"npoints": npoints, "count_time": count_time})

    _log.info("Doing %s", scan_type)

    scan_params = {"npoints": npoints, "count_time": count_time, "type": scan_type}

    chain = DEFAULT_CHAIN.get(scan_info, counter_args)

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


@typeguard.typechecked
def loopscan(
    npoints: int,
    count_time: float,
    *counter_args: _countables,
    name: str = "loopscan",
    title: Optional[str] = None,
    scan_type: str = "loopscan",
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
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

    if title is None:
        args = scan_type, npoints, count_time
        template = " ".join(["{{{0}}}".format(i) for i in range(len(args))])
        title = template.format(*args)

    return timescan(
        count_time,
        *counter_args,
        npoints=npoints,
        name=name,
        title=title,
        scan_type=scan_type,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


@typeguard.typechecked
def ct(
    count_time: float,
    *counter_args: _countables,
    name: str = "ct",
    title: Optional[str] = None,
    save: bool = False,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
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


# Todo: should this define start,stop? why is there total_acq_time?
@typeguard.typechecked
def pointscan(
    motor: _scannable,
    positions: _position_list,
    count_time: float,
    *counter_args: _countables,
    name: str = "pointscan",
    title: Optional[str] = None,
    scan_type: str = "pointscan",
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
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
        run (bool): True by default
    """

    return lookupscan(
        [(motor, positions)],
        count_time,
        *counter_args,
        scan_type=scan_type,
        name=name,
        title=title,
        save=save,
        save_images=save_images,
        sleep_time=sleep_time,
        run=run,
        return_scan=return_scan,
        scan_info=scan_info,
    )


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
    return scan.goto_peak(counter_name, axis=axis)


def where():
    for axis in last_scan_motors():
        current_session.scans[-1].where(axis=axis)
