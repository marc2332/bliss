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
    'mesh',
    'dscan',
    'd2scan',
    'timescan',
    'loopscan',
    'ct',
    'get_data']


import logging
import operator
import warnings

from bliss import setup_globals

from bliss.data.scan import get_data

from bliss.common.task_utils import *
from bliss.common import measurementgroup
from bliss.common.motor_group import Group
from bliss.common.axis import estimate_duration
from bliss.common.utils import OrderedDict as ordereddict
from bliss.common.measurement import BaseCounter, Counter
from bliss.common.measurement import SamplingCounter, IntegratingCounter
from bliss.common.temperature import Input, Output, TempControllerCounter

from bliss.scanning import scan as scan_module
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import VariableStepTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster, MeshStepTriggerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice, IntegratingCounterAcquisitionDevice


_log = logging.getLogger('bliss.scans')


class TimestampPlaceholder:
    def __init__(self):
        self.name = 'timestamp'


def _get_object_from_name(name):
    """Get the bliss object corresponding to the given name."""
    try:
        return operator.attrgetter(name)(setup_globals)
    except AttributeError:
        raise AttributeError(name)


def _get_counters_from_measurement_group(mg):
    """Get the counters from a measurement group."""
    counters, missing = [], []
    for name in mg.enabled:
        try:
            obj = _get_object_from_name(name)
        except AttributeError:
            missing.append(name)
        else:
            # Prevent groups from pointing to other groups
            counters += _get_counters_from_object(obj, recursive=False)
    if missing:
        raise AttributeError(*missing)
    return counters


def _get_counters_from_object(arg, recursive=True):
    """Get the counters from a bliss object (typically a scan function
    positional counter argument).

    According to issue #251, `arg` can be:
    - a counter
    - a counter namepace
    - a controller, in which case:
       - controller.groups.default namespace is used if it exists
       - controller.counters namepace otherwise
    - a measurementgroup
    """
    if isinstance(arg, measurementgroup.MeasurementGroup):
        if not recursive:
            raise ValueError(
                'Measurement groups cannot point to other groups')
        return _get_counters_from_measurement_group(arg)
    try:
        return arg.counter_groups.default
    except AttributeError:
        pass
    try:
        return arg.counters
    except AttributeError:
        pass
    try:
        return list(arg)
    except TypeError:
        return [arg]


def get_all_counters(counter_args):
    # Use active MG if no counter is provided
    if not counter_args:
        active = measurementgroup.get_active()
        if active is None:
            raise ValueError(
                'No measurement group is currently active')
        counter_args = [active]

    # Initialize
    all_counters, missing = [], []

    # Process all counter arguments
    for obj in counter_args:
        try:
            all_counters += _get_counters_from_object(obj)
        except AttributeError as exc:
            missing += exc.args

    # Missing counters
    if missing:
        raise ValueError(
            "Missing counters, not in setup_globals: {}.\n"
            "Hint: disable inactive counters."
            .format(', '.join(missing)))

    return all_counters


def activate_master_saving(acq_device, activate_flag):
    acq_device.save_flag = activate_flag


def counter_tree(counters, scan_pars):
    """Create the counter tree from a given counter list.

    It relies on four standard methods:
    - counter.master_controller.create_master_device
    - counter.create_acquisition_device
    - acquisition_master.add_counter
    - acquisition_device.add_counter
    """
    # Initialize structures
    master_dict = {}
    device_dict = {}
    tree = ordereddict()

    # Loop over counters
    for counter in counters:

        # Create master
        master_controller = counter.master_controller
        if master_controller and master_controller not in master_dict:
            master_dict[master_controller] = \
                master_controller.create_master_device(scan_pars)

        # Make sure the master is in the tree
        acquisition_master = master_dict.get(master_controller)
        tree.setdefault(acquisition_master, [])

        # Create device
        device_controller = counter.controller
        if device_controller and device_controller not in device_dict:
            acquisition_device = counter.create_acquisition_device(scan_pars)
            device_dict[device_controller] = acquisition_device

        # Make sure the device is in the tree
        if acquisition_device not in tree[acquisition_master]:
            tree[acquisition_master].append(acquisition_device)

        # Add counter
        if device_controller:
            device_dict[device_controller].add_counter(counter)
        elif master_controller:
            master_dict[master_controller].add_counter(counter)
        else:
            warnings.warn(
                'Counter {!r} has no controller associated'.format(counter))

    return tree


def default_chain(chain, scan_pars, counter_args):
    # Scan parameters
    count_time = scan_pars.get('count_time', 1)
    sleep_time = scan_pars.get('sleep_time')
    npoints = scan_pars.get('npoints', 1)

    # Issue warning for non BaseCounter instance (for the moment)
    def get_name(counter):
        if not isinstance(counter, BaseCounter):
            warnings.warn('{!r} is not a counter'.format(counter))
            return counter.name
        return counter.fullname

    # Remove duplicates
    counter_dct = {
        get_name(counter): counter
        for counter in get_all_counters(counter_args)}

    # Sort counters
    counters = [
        counter for name, counter in
        sorted(counter_dct.items())]

    # No counters
    if not counters:
        raise ValueError(
            "No counters for scan. Hint: are all counters disabled ?")

    # Build default master
    timer = SoftwareTimerMaster(
        count_time,
        npoints=npoints,
        sleep_time=sleep_time)

    # Build counter tree
    tree = counters_tree(counters, scan_pars)

    # Build chain
    for acq_master, acq_devices in tree.iteritems():
        if acq_master:
            chain.add(timer, acq_master)
        else:
            acq_master = timer
        for acq_device in acq_devices:
            chain.add(acq_master, acq_device)

    # Return timer
    chain.timer = timer
    return timer


def step_scan(chain, scan_info, name=None, save=True):
    scan_data_watch = scan_module.StepScanDataWatch()
    config = scan_module.ScanSaving().get()
    writer = config.get("writer") if save else None
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

    Use `ascan(..., run=False, return_scan=True)` to create a scan object and
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
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): False by default
    """
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

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, _get_all_counters(counters))
    top_master = LinearStepTriggerMaster(npoints, motor, start, stop)
    chain.add(top_master, timer)

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, start, stop, npoints)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "ascan"),
        save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', False):
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

    Use `dscan(..., run=False, return_scan=True)` to create a scan object and
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
        return_scan (bool): False by default
    """
    kwargs['type'] = 'dscan'
    oldpos = motor.position()
    scan = ascan(motor, oldpos + start, oldpos + stop, npoints, count_time,
                 *counter_args, **kwargs)
    motor.move(oldpos)
    return scan


def mesh(
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

    The mesh scan traces out a grid using motor1 and motor2. The first motor
    scans from start1 to end1 using the specified number of intervals.  The
    second motor similarly scans from start2 to end2. Each point is counted for
    for time seconds (or monitor counts).

    The scan of motor1 is done at each point scanned by motor2.  That is, the
    first motor scan is nested within the second motor scan.

    Use `mesh(..., run=False, return_scan=True)` to create a scan object and
    its acquisition chain without executing the actual scan.

    """
    scan_info = {'type': kwargs.get('type', 'mesh'),
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
                      estimate_duration(motor1, end1, start1))
    total_motion_t2 = npoints2 * n_motion_t2

    imotion_t = max(i_motion_t1, i_motion_t2)

    total_motion_t = imotion_t + total_motion_t1 + total_motion_t2
    total_count_t = npoints1 * npoints2 * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}

    scan_info.update({'npoints1': npoints1, 'npoints2': npoints2,
                      'total_acq_time': total_count_t,
                      'start': [start1, start2], 'stop': [stop1, stop2],
                      'count_time': count_time,
                      'estimation': estimation})

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counter_args)
    top_master = MeshStepTriggerMaster(motor1, start1, stop1, npoints1,
                                       motor2, start2, stop2, npoints2)
    chain.add(top_master, timer)

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
            "mesh"),
        save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', False):
        return scan


def a2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *counter_args, **kwargs):
    """
    Absolute 2 motor scan

    Scans two motors, as specified by *motor1* and *motor2*. The motors start
    at the positions given by *start1* and *start2* and end at the positions
    given by *stop1* and *stop2*. The step size for each motor is given by
    `(*start*-*stop*)/(*npoints*-1)`. The number of intervals will be
    *npoints*-1. Count time is given by *count_time* (seconds).

    Use `a2scan(..., run=False, return_scan=True)` to create a scan object and
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
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): False by default
    """
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

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counter_args)
    top_master = LinearStepTriggerMaster(npoints,
                                         motor1, start1, stop1,
                                         motor2, start2, stop2)
    chain.add(top_master, timer)

    _log.info(
        "Scanning %s from %f to %f and %s from %f to %f in %d points",
        motor1.name, start1, stop1, motor2.name, start2, stop2, npoints)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "a2scan"),
        save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', False):
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

    Use `d2scan(..., run=False, return_scan=True)` to create a scan object and
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
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): False by default
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

    Use `timescan(..., run=False, return_scan=True)` to create a scan object and
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
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): False by default
        npoints (int): number of points [default: 0, meaning infinite number of points]
        output_mode (str): valid are 'tail' (append each line to output) or
                           'monitor' (refresh output in single line)
                           [default: 'tail']
    """
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

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counter_args)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "timescan"),
        save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', False):
        return scan


def loopscan(npoints, count_time, *counter_args, **kwargs):
    """
    Similar to :ref:`timescan` but npoints is mandatory

    Use `loopscan(..., run=False, return_scan=True)` to create a scan object and
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
        return_scan (bool): False by default
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

    Use `ct(..., run=False, return_scan=True)` to create a count object and
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
        return_scan (bool): False by default
    """
    kwargs['type'] = 'ct'
    kwargs['save'] = False
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
        return_scan (bool): False by default
    """
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

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counter_args)
    top_master = VariableStepTriggerMaster(motor, positions)
    chain.add(top_master, timer)

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, positions[0], positions[npoints - 1], npoints)

    scan = step_scan(
        chain,
        scan_info,
        name=kwargs.setdefault(
            "name",
            "pointscan"),
        save=scan_info['save'])
    scan.run()
    if kwargs.get('return_scan', False):
        return scan
