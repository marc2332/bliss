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
    "lineup",
    "timescan",
    "loopscan",
    "lookupscan",
    "pointscan",
    "DEFAULT_CHAIN",
]

import logging
import numpy
import types
import typeguard
from typing import Optional

from bliss.common.utils import rounder, shorten_signature, typeguardTypeError_to_hint
from bliss.common.cleanup import cleanup, axis as cleanup_axis
from bliss.scanning.toolbox import DefaultAcquisitionChain
from bliss.scanning.scan import Scan, StepScanDataWatch
from bliss.scanning.acquisition.motor import VariableStepTriggerMaster
from bliss.scanning.scan_info import ScanInfo
from bliss.common.protocols import Scannable
from bliss.common.types import (
    _int,
    _float,
    _countable,
    _countables,
    _scannable_start_stop_list,
    _position_list,
    _scannable_position_list,
)

_log = logging.getLogger("bliss.scans")

DEFAULT_CHAIN = DefaultAcquisitionChain()


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def ascan(
    motor: Scannable,
    start: _float,
    stop: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    Absolute scan

    Scans one motor, as specified by *motor*. The motor starts at the position
    given by *start* and ends at the position given by *stop*. The step size is
    `(*start*-*stop*)/*intervals*`. Count time is given by *count_time* (seconds).

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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def dscan(
    motor: Scannable,
    start: _float,
    stop: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def lineup(
    motor: Scannable,
    start: _float,
    stop: _float,
    intervals: _int,
    count_time: _float,
    counter: _countable,
    name: str = "lineup",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def a2scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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
@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
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
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,
    restore_motor_positions: bool = False,
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
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,
    restore_motor_positions: bool = False,
    """
    scan_info = ScanInfo.normalize(scan_info)
    if scan_params is None:
        scan_params = dict()

    npoints = len(motor_pos_tuple_list[0][1])
    motors_positions = list()
    scan_axes = set()

    for m_tup in motor_pos_tuple_list:
        mot = m_tup[0]
        if mot in scan_axes:
            raise ValueError(f"Duplicated axis {mot.name}")
        scan_axes.add(mot)
        assert len(m_tup[1]) == npoints
        motors_positions.extend((mot, m_tup[1]))

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

    # Specify a default plot if it is not already the case
    if not scan_info.has_default_curve_plot():
        time_channel = chain.timer.channels[0]
        scan_info.add_curve_plot(x=time_channel.fullname)

    scan = Scan(
        chain,
        scan_info=scan_info,
        name=name,
        save=save,
        save_images=save_images,
        data_watch_callback=StepScanDataWatch(),
    )

    if restore_motor_positions:
        scan.restore_motor_positions = True

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
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    scan_type: Optional[str] = None,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    restore_motor_positions: bool = False,
):
    """
    anscan usage:
      anscan( [(m1, start_m1_pos, stop_m1_pos), (m2, start_m2_pos, stop_m2_pos)], intervals, ctime, *counter_args)
    10 points scan at 0.1 second integration on motor **m1** from
    *stop_m1_pos* to *stop_m1_pos* and **m2** from *start_m2_pos* to
    *stop_m2_pos* and with one counter.
    
    arguments:
    motor_tuple_list: a list of tuples of the following type (motor,start,stop)
    intervals: number of intervals
    count_time: count time in seconds
    *counter_args: as many counter-providing objects as used in the scan (seperated by comma)
    
    keyword arguments:
    scan_type: str = "lookupscan",
    name: str = "lookupscan",
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,
    restore_motor_positions: bool = False,

    example:
      anscan( [(m1, 1, 2), (m2, 3, 7)], 10, 0.1, diode2)
    10 points scan at 0.1 second integration on motor **m1** from
    1 to 2 and **m2** from 3 to 7 and with diode2 as the only counter.
    """

    npoints = intervals + 1

    scan_info = ScanInfo.normalize(scan_info)

    motors_positions = list()
    title_list = list()
    starts_list = list()
    stops_list = list()
    scan_axes = set()
    for m_tup in motor_tuple_list:
        mot = m_tup[0]
        if mot in scan_axes:
            raise ValueError(f"Duplicated axis {mot.name}")
        scan_axes.add(mot)
        d = mot._set_position if scan_type == "dscan" else 0
        start = m_tup[1] + d
        stop = m_tup[2] + d
        title_list.extend(
            (mot.name, rounder(mot.tolerance, start), rounder(mot.tolerance, stop))
        )
        motors_positions.append((mot, numpy.linspace(start, stop, npoints)))
        starts_list.append(start)
        stops_list.append(stop)

    # Specify a default plot if it is not already the case
    if not scan_info.has_default_curve_plot():
        mot = motor_tuple_list[0][0]
        scan_info.add_curve_plot(x=f"axis:{mot.name}")

    scan_info["start"] = starts_list
    scan_info["stop"] = stops_list

    for motor, start, stop in motor_tuple_list:
        d = motor.position if scan_type == "dscan" else 0
        scan_info.set_channel_meta(
            f"axis:{motor.name}", start=start + d, stop=stop + d, points=npoints
        )

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
        args = [scan_type.replace("d", "a")]
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
        restore_motor_positions=restore_motor_positions,
    )


@typeguard.typechecked
def dnscan(
    motor_tuple_list: _scannable_start_stop_list,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    scan_type: Optional[str] = None,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
):
    """
    dnscan usage:
      dnscan([(m0, rel_start_m0, rel_end_m0), (m1, rel_start_m1, rel_stop_m1)], 10, 0.1, counter)
    
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
    sleep_time: Optional[_float] = None,
    run: bool = True,
    return_scan: bool = True,
    scan_info: Optional[dict] = None,
    scan_params: Optional[dict] = None,

    
    example:
      dnscan([(m0, -1, 1),(m1, -2, 2)], 10, 0.1, diode2)
    """

    scan = anscan(
        motor_tuple_list,
        intervals,
        count_time,
        *counter_args,
        save=save,
        save_images=save_images,
        title=title,
        name=name,
        scan_type="dscan",
        sleep_time=sleep_time,
        run=False,
        scan_info=scan_info,
        restore_motor_positions=True,
    )

    if run:
        scan.run()

    if return_scan:
        return scan


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def a3scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    motor3: Scannable,
    start3: _float,
    stop3: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def a4scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    motor3: Scannable,
    start3: _float,
    stop3: _float,
    motor4: Scannable,
    start4: _float,
    stop4: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def a5scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    motor3: Scannable,
    start3: _float,
    stop3: _float,
    motor4: Scannable,
    start4: _float,
    stop4: _float,
    motor5: Scannable,
    start5: _float,
    stop5: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def d3scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    motor3: Scannable,
    start3: _float,
    stop3: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def d4scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    motor3: Scannable,
    start3: _float,
    stop3: _float,
    motor4: Scannable,
    start4: _float,
    stop4: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def d5scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    motor3: Scannable,
    start3: _float,
    stop3: _float,
    motor4: Scannable,
    start4: _float,
    stop4: _float,
    motor5: Scannable,
    start5: _float,
    stop5: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def d2scan(
    motor1: Scannable,
    start1: _float,
    stop1: _float,
    motor2: Scannable,
    start2: _float,
    stop2: _float,
    intervals: _int,
    count_time: _float,
    *counter_args: _countables,
    name: Optional[str] = None,
    title: Optional[str] = None,
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        intervals,
        count_time,
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


@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def timescan(
    count_time: _float,
    *counter_args: _countables,
    npoints: Optional[_int] = 0,
    name: str = "timescan",
    title: Optional[str] = None,
    scan_type: str = "timescan",
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        title (str): scan title [default: 'timescan <count_time> <npoints>]
        save (bool): save scan data to file [default: True]
        save_images (bool or None): save image files [default: None, means it follows 'save']
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
        npoints (int): number of points [default: 0, meaning infinite number of points]
    """
    scan_info = ScanInfo.normalize(scan_info)

    scan_info.update({"type": scan_type, "save": save, "sleep_time": sleep_time})

    if title is None:
        if npoints == 0:
            title = f"{scan_type} {count_time}"
        else:
            title = f"{scan_type} {count_time} {npoints}"

    scan_info.update({"npoints": npoints, "count_time": count_time, "title": title})

    _log.info("Doing %s", scan_type)

    scan_params = {
        "npoints": npoints,
        "count_time": count_time,
        "type": scan_type,
        "sleep_time": sleep_time,
    }
    chain = DEFAULT_CHAIN.get(scan_params, counter_args)

    # Specify a default plot if it is not already the case
    if npoints > 1:
        # No plots are created for ct
        if not scan_info.has_default_curve_plot():
            time_channel = chain.timer.channels[0]
            scan_info.add_curve_plot(x=time_channel.fullname)

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
def loopscan(
    npoints: _int,
    count_time: _float,
    *counter_args: _countables,
    name: str = "loopscan",
    title: Optional[str] = None,
    scan_type: str = "loopscan",
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
        title (str): scan title [default: 'timescan <npoints> <count_time>']
        save (bool): save scan data to file [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """

    if title is None:
        title = f"{scan_type} {npoints} {count_time}"

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


# Todo: should this define start,stop? why is there total_acq_time?
@typeguardTypeError_to_hint
@shorten_signature(hidden_kwargs=["title", "name", "scan_type", "return_scan"])
@typeguard.typechecked
def pointscan(
    motor: Scannable,
    positions: _position_list,
    count_time: _float,
    *counter_args: _countables,
    name: str = "pointscan",
    title: Optional[str] = None,
    scan_type: str = "pointscan",
    save: bool = True,
    save_images: Optional[bool] = None,
    sleep_time: Optional[_float] = None,
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
