# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Most common scan procedures (:func:`~bliss.common.scans.ascan`, \
:func:`~bliss.common.scans.dscan`, :func:`~bliss.common.scans.timescan`, etc)

"""

__all__ = [
    'ascan',
    'a2scan',
    'amesh',
    'dscan',
    'lineup',
    'd2scan',
    'timescan',
    'loopscan',
    'ct',
    'DEFAULT_CHAIN']

import logging

from bliss.common.motor_group import Group
from bliss.common.cleanup import cleanup, axis as cleanup_axis
from bliss.common.axis import estimate_duration
from bliss.scanning.default import DefaultAcquisitionChain
from bliss.scanning import scan as scan_module
from bliss.scanning.acquisition.motor import VariableStepTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster, MeshStepTriggerMaster

_log = logging.getLogger('bliss.scans')

DEFAULT_CHAIN = DefaultAcquisitionChain()

def step_scan(chain, scan_info, name=None, save=True, save_images=True):
    scan_data_watch = scan_module.StepScanDataWatch()
    config = scan_module.ScanSaving().get()
    writer = config.get("writer") if save else None
    if writer:
        writer._save_images = save_images
    return scan_module.Scan(chain,
                            name=name,
                            parent=config['parent'],
                            scan_info=scan_info,
                            writer=writer,
                            data_watch_callback=scan_data_watch)


def ascan(motor, start, stop, npoints, count_time, *counter_args, **kwargs):
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
        npoints (int): the number of points
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'ascan <motor> ... <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool): save image files [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    save_images = kwargs.pop('save_images', True)

    scan_info = {'type': kwargs.get('type', 'ascan'),
                 'save': kwargs.get('save', True),
                 'title': kwargs.get('title'),
                 'sleep_time': kwargs.get('sleep_time')}

    if scan_info['title'] is None:
        args = scan_info['type'], motor.name, start, stop, npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    # estimate scan time
    step_size = abs(stop - start) / float(npoints)
    i_motion_t = estimate_duration(motor, start)
    n_motion_t = estimate_duration(motor, start, start + step_size)
    total_motion_t = i_motion_t + npoints * n_motion_t
    total_count_t = npoints * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}

    scan_info.update({'npoints': npoints, 'total_acq_time': total_count_t,
                      'start': [start], 'stop': [stop],
                      'count_time': count_time,
                      'estimation': estimation})

    chain = DEFAULT_CHAIN.get(scan_info, counter_args,
                              top_master=LinearStepTriggerMaster(npoints,
                                                                 motor, start,
                                                                 stop))

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, start, stop, npoints)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "ascan"),
        save=scan_info['save'],
        save_images=save_images)

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', True):
        return scan


def dscan(motor, start, stop, npoints, count_time, *counter_args, **kwargs):
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
        npoints (int): the number of points
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
    kwargs['type'] = 'dscan'
    kwargs.setdefault('name', 'dscan')
    start += motor.position()
    stop += motor.position()
    with cleanup(motor, restore_list=(cleanup_axis.POS,)):
        scan = ascan(motor, start, stop, npoints, count_time,
                     *counter_args, **kwargs)
    return scan


def lineup(motor, start, stop, npoints, count_time, *counter_args, **kwargs):
    if len(counter_args) == 0:
        raise ValueError("lineup: please specify a counter")
    if len(counter_args) > 1:
        raise ValueError("lineup: too many counters")

    kwargs['type'] = 'lineup'
    kwargs['name'] = kwargs.get('name', 'lineup')
    kwargs['return_scan'] = True
    scan = dscan(motor, start, stop, npoints, count_time, counter_args[0],
                 **kwargs)
    scan.goto_peak(counter_args[0])

def amesh(
        motor1,
        start1,
        stop1,
        npoints1,
        motor2,
        start2,
        stop2,
        npoints2,
        count_time,
        *counter_args,
        **kwargs):
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
    save_images = kwargs.pop('save_images', True)

    scan_info = {'type': kwargs.get('type', 'amesh'),
                 'save': kwargs.get('save', True),
                 'title': kwargs.get('title'),
                 'sleep_time': kwargs.get('sleep_time')}

    if scan_info['title'] is None:
        args = scan_info['type'], motor1.name, start1, stop1, npoints1, \
            motor2.name, start2, stop2, npoints2, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    # estimate scan time
    step_size1 = abs(stop1 - start1) / float(npoints1)
    i_motion_t1 = estimate_duration(motor1, start1)
    n_motion_t1 = estimate_duration(motor1, start1, start1 + step_size1)
    total_motion_t1 = npoints1 * npoints2 * n_motion_t1

    step_size2 = abs(stop2 - start2) / float(npoints2)
    i_motion_t2 = estimate_duration(motor2, start2)
    n_motion_t2 = max(estimate_duration(motor2, start2, start2 + step_size2),
                      estimate_duration(motor1, stop1, start1))
    total_motion_t2 = npoints2 * n_motion_t2

    imotion_t = max(i_motion_t1, i_motion_t2)

    total_motion_t = imotion_t + total_motion_t1 + total_motion_t2
    total_count_t = npoints1 * npoints2 * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}

    scan_info.update({'npoints1': npoints1,
                      'npoints2': npoints2,
                      'npoints': npoints1 * npoints2,
                      'total_acq_time': total_count_t,
                      'start': [start1, start2],
                      'stop': [stop1, stop2],
                      'count_time': count_time,
                      'estimation': estimation})

    backnforth = kwargs.pop('backnforth', False)
    chain = DEFAULT_CHAIN.get(scan_info, counter_args, top_master=MeshStepTriggerMaster(motor1, start1, stop1, npoints1,
                                       motor2, start2, stop2,
                                                                                        npoints2,backnforth=backnforth))

    _log.info(
        "Scanning (%s, %s) from (%f, %f) to (%f, %f) in (%d, %d) points",
        motor1.name,
        motor2.name,
        start1,
        start2,
        stop1,
        stop2,
        npoints1,
        npoints2)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "amesh"),
        save=scan_info['save'],
        save_images=save_images)

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', True):
        return scan

def dmesh(
        motor1,
        start1,
        stop1,
        npoints1,
        motor2,
        start2,
        stop2,
        npoints2,
        count_time,
        *counter_args,
        **kwargs):
    """Relative amesh
    """
    kwargs['type'] = 'dmesh'
    kwargs.setdefault("name", "dmesh")
    start1 += motor1.position()
    stop1 += motor1.position()
    start2 += motor2.position()
    stop2 += motor2.position()

    with cleanup(motor1, motor2, restore_list=(cleanup_axis.POS, )):
        return amesh(motor1, start1, stop1, npoints1, motor2, start2, stop2, npoints2, count_time, *counter_args, **kwargs)

def a2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *counter_args, **kwargs):
    """
    Absolute 2 motor scan

    Scans two motors, as specified by *motor1* and *motor2*. The motors start
    at the positions given by *start1* and *start2* and end at the positions
    given by *stop1* and *stop2*. The step size for each motor is given by
    `(*start*-*stop*)/(*npoints*-1)`. The number of intervals will be
    *npoints*-1. Count time is given by *count_time* (seconds).

    Use `a2scan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        motor1 (Axis): motor1 to scan
        start1 (float): motor1 start position
        stop1 (float): motor1 end position
        motor2 (Axis): motor2 to scan
        start2 (float): motor2 start position
        stop2 (float): motor2 end position
        npoints (int): the number of points
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'a2scan <motor1> ... <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool): save image files [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    save_images = kwargs.pop('save_images', True)

    scan_info = {'type': kwargs.get('type', 'a2scan'),
                 'save': kwargs.get('save', True),
                 'title': kwargs.get('title'),
                 'sleep_time': kwargs.get('sleep_time')}

    if scan_info['title'] is None:
        args = scan_info['type'], motor1.name, start1, stop1, \
            motor2.name, start2, stop2, npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    # estimate scan time
    step_size1 = abs(stop1 - start1) / float(npoints)
    i_motion1_t = estimate_duration(motor1, start1)
    n_motion1_t = estimate_duration(motor1, start1, start1 + step_size1)

    step_size2 = abs(stop2 - start2) / float(npoints)
    i_motion2_t = estimate_duration(motor2, start2)
    n_motion2_t = estimate_duration(motor2, start2, start2 + step_size2)

    i_motion_t = max(i_motion1_t, i_motion2_t)
    n_motion_t = max(n_motion1_t, n_motion2_t)
    total_motion_t = i_motion_t + npoints * n_motion_t
    total_count_t = npoints * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}

    scan_info.update({'npoints': npoints, 'total_acq_time': total_count_t,
                      'start': [start1, start2], 'stop': [stop1, stop2],
                      'count_time': count_time,
                      'estimation': estimation})

    chain = DEFAULT_CHAIN.get(scan_info, counter_args, top_master=LinearStepTriggerMaster(npoints,
                                         motor1, start1, stop1,
                                         motor2, start2, stop2))

    _log.info(
        "Scanning %s from %f to %f and %s from %f to %f in %d points",
        motor1.name, start1, stop1, motor2.name, start2, stop2, npoints)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "a2scan"),
        save=scan_info['save'],
        save_images=save_images)

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', True):
        return scan


def d2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *counter_args, **kwargs):
    """
    Relative 2 motor scan

    Scans two motors, as specified by *motor1* and *motor2*. Each motor moves
    the same number of points. If a motor is at position *X*
    before the scan begins, the scan will run from `X+start` to `X+end`.
    The step size of a motor is `(*start*-*stop*)/(*npoints*-1)`. The number
    of intervals will be *npoints*-1. Count time is given by *count_time*
    (seconds).

    At the end of the scan (even in case of error) the motor will return to
    its initial position

    Use `d2scan(..., run=False)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        motor1 (Axis): motor1 to scan
        start1 (float): motor1 relative start position
        stop1 (float): motor1 relative end position
        motor2 (Axis): motor2 to scan
        start2 (float): motor2 relative start position
        stop2 (float): motor2 relative end position
        npoints (int): the number of points
        count_time (float): count time (seconds)
        counter_args (counter-providing objects):
            each argument provides counters to be integrated in the scan.
            if no counter arguments are provided, use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'd2scan <motor1> ... <count_time>']
        save (bool): save scan data to file [default: True]
        save_images (bool): save image files [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
    """
    kwargs['type'] = 'd2scan'

    oldpos1 = motor1.position()
    oldpos2 = motor2.position()

    kwargs.setdefault('name', 'd2scan')

    scan = a2scan(
        motor1,
        oldpos1 + start1,
        oldpos1 + stop1,
        motor2,
        oldpos2 + start2,
        oldpos2 + stop2,
        npoints,
        count_time,
        *counter_args,
        **kwargs)

    group = Group(motor1, motor2)
    group.move(motor1, oldpos1, motor2, oldpos2)
    return scan


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
        save_images (bool): save image files [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): True by default
        npoints (int): number of points [default: 0, meaning infinite number of points]
        output_mode (str): valid are 'tail' (append each line to output) or
                           'monitor' (refresh output in single line)
                           [default: 'tail']
    """
    save_images = kwargs.get('save_images', True)

    scan_info = {'type': kwargs.get('type', 'timescan'),
                 'save': kwargs.get('save', True),
                 'title': kwargs.get('title'),
                 'sleep_time': kwargs.get('sleep_time'),
                 'output_mode': kwargs.get('output_mode', 'tail')}

    if scan_info['title'] is None:
        args = scan_info['type'], count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    npoints = kwargs.get("npoints", 0)
    total_count_t = npoints * count_time

    scan_info.update({'npoints': npoints, 'total_acq_time': total_count_t,
                      'start': [], 'stop': [], 'count_time': count_time})

    if npoints > 0:
        # estimate scan time
        estimation = {'total_motion_time': 0,
                      'total_count_time': total_count_t,
                      'total_time': total_count_t}
        scan_info['estimation'] = estimation

    _log.info("Doing %s", scan_info['type'])

    chain = DEFAULT_CHAIN.get(scan_info, counter_args)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "timescan"),
        save=scan_info['save'],
        save_images=save_images)

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', True):
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
    kwargs.setdefault('npoints', npoints)
    kwargs.setdefault('name', 'loopscan')
    return timescan(count_time, *counter_args, **kwargs)


def ct(count_time, *counter_args, **kwargs):
    """
    Count for a specified time

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
    kwargs['type'] = 'ct'
    kwargs.setdefault('save', False)
    kwargs['npoints'] = 1

    kwargs.setdefault("name", "ct")

    return timescan(count_time, *counter_args, **kwargs)


def pointscan(motor, positions, count_time, *counter_args, **kwargs):
    """
    Point scan

    Scans one motor, as specified by *motor*. The motor starts at the position
    given by the first value in *positions* and ends at the position given by last value *positions*.
    Count time is given by *count_time* (seconds).

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
        save_images (bool): save image files [default: True]
        return_scan (bool): True by default
    """
    save_images = kwargs.pop('save_images', True)

    scan_info = {'type': kwargs.get('type', 'pointscan'),
                 'save': kwargs.get('save', True),
                 'title': kwargs.get('title')}

    npoints = len(positions)
    if scan_info['title'] is None:
        args = scan_info['type'], motor.name, positions[0], positions[npoints -
                                                                      1], npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    scan_info.update(
        {'npoints': npoints, 'total_acq_time': npoints * count_time,
         'start': positions[0],
         'stop': positions[npoints - 1],
         'count_time': count_time})

    chain = DEFAULT_CHAIN.get(scan_info, counter_args,
                              top_master=VariableStepTriggerMaster(motor,
                                                                   positions))

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, positions[0], positions[npoints - 1], npoints)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "pointscan"),
        save=scan_info['save'],
        save_images=save_images)

    scan.run()
    if kwargs.get('return_scan', True):
        return scan
