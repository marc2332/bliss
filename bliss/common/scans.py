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

__all__ = ['ascan', 'a2scan', 'mesh', 'dscan', 'd2scan', 'timescan', 'loopscan',
           'ct', 'get_data']

import time
import logging
import operator
import functools
import numpy
import gevent

from bliss import setup_globals
from bliss.common.axis import MotionEstimation
from bliss.common.temperature import Input, Output, TempControllerCounter
from bliss.controllers.lima import Lima
from bliss.common.task_utils import *
from bliss.common.motor_group import Group
from bliss.common.measurement import Counter, SamplingCounter, IntegratingCounter
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice, IntegratingCounterAcquisitionDevice
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning import scan as scan_module
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster, MeshStepTriggerMaster
from bliss.scanning.acquisition.lima import LimaAcquisitionMaster
from bliss.session import session,measurementgroup
try:
    from bliss.scanning.writer import hdf5 as default_writer
except ImportError:
    default_writer = None
from bliss.data.scan import get_data
from bliss.common.utils import OrderedDict as ordereddict

_log = logging.getLogger('bliss.scans')


class TimestampPlaceholder:
    def __init__(self):
      self.name = 'timestamp'

def _get_counters(mg, missing_list):
    counters = list()
    if mg is not None:
        for cnt_name in mg.enable:
            cnt = operator.attrgetter(cnt_name)(setup_globals)
            if cnt:
                counters.append(cnt)
            else:
                missing_list.append(cnt_name)
    return counters

def _get_all_counters(counters):
    all_counters, missing_counters = [], []
    if counters:
        for cnt in counters:
            if isinstance(cnt, measurementgroup.MeasurementGroup):
                all_counters.extend(_get_counters(cnt, missing_counters))
            else:
                all_counters.append(cnt)
    else:
        all_counters.extend(_get_counters(measurementgroup.get_active(), 
                                          missing_counters))
    
    if missing_counters:
        raise ValueError("Missing counters, not in setup_globals: %s. " \
                         "Hint: disable inactive counters."
                         % ", ".join(missing_counters))

    zerod_counters = list()
    other_counters = list()
    for counter in all_counters:
        if isinstance(counter, Counter):
            zerod_counters.append(counter)
        else:
            other_counters.append(counter)
    return zerod_counters,other_counters

def default_master_configuration(counter, scan_pars):
    """
    This function should create and configure
    an acquisition device which could also
    be a master for other devices.

    @returns the acq_device + counters parameters
    """
    try:
        device = counter.acquisition_controller
    except AttributeError:
        device = counter

    if isinstance(device, Lima):
        multi_mode = 'INTERNAL_TRIGGER_MULTI' in device.available_triggers
        save_flag = scan_pars.get('save',False)
        acq_nb_frames = scan_pars.get('npoints',1) if multi_mode else 1
        acq_expo_time = scan_pars['count_time']
        acq_trigger_mode = scan_pars.get('acq_trigger_mode',
                                         'INTERNAL_TRIGGER_MULTI' \
                                         if multi_mode else 'INTERNAL_TRIGGER')
        acq_device = LimaAcquisitionMaster(device,
                                           acq_nb_frames = acq_nb_frames,
                                           acq_expo_time = acq_expo_time,
                                           acq_trigger_mode = acq_trigger_mode,
                                           save_flag = save_flag,
                                           prepare_once = multi_mode)
        return acq_device, { "prepare_once": multi_mode, "start_once": multi_mode }
    else:
        raise TypeError("`%r' is not a supported acquisition controller for counter `%s'" % (device, counter.name))

def activate_master_saving(acq_device,activate_flag):
    acq_device.save_flag = activate_flag

def _counters_tree(counters, scan_pars):
    count_time = scan_pars.get('count_time', 1)
    npoints = scan_pars.get('npoints', 1)
    master_integrating_counter = dict()
    tree = ordereddict()
 
    reader_counters = ordereddict()
    for cnt in counters:
        ###THIS SHOULD GO AWAY
        if isinstance(cnt, (Input, Output)):
            cnt = TempControllerCounter(cnt.name, cnt)
        ###
        grouped_read_handler = Counter.GROUPED_READ_HANDLERS.get(cnt)
        if grouped_read_handler:
            reader_counters.setdefault(grouped_read_handler, list()).append(cnt)
        else:
            reader_counters[cnt] = []

    for reader, counters in reader_counters.iteritems():
        if isinstance(reader, (SamplingCounter.GroupedReadHandler, SamplingCounter)):
            acq_device = SamplingCounterAcquisitionDevice(reader, **scan_pars)
            for cnt in counters:
                acq_device.add_counter(cnt)
            tree.setdefault(None, list()).append(acq_device)
        elif isinstance(reader, (IntegratingCounter.GroupedReadHandler, IntegratingCounter)):
            try:
                cnt = counters[0] #the first counter is used to determine master acq device
            except IndexError:
                cnt = reader
            master_acq_device = master_integrating_counter.get(cnt.acquisition_controller)
            if master_acq_device is None:
                tmp_scan_pars = scan_pars.copy()
                # by default don't save data from master
                # so pop **save** flag
                tmp_scan_pars.pop('save',None)
                master_acq_device, _ = default_master_configuration(cnt, tmp_scan_pars)
                master_integrating_counter[cnt.acquisition_controller] = master_acq_device
            if isinstance(reader, IntegratingCounter.GroupedReadHandler):
                acq_device = IntegratingCounterAcquisitionDevice(reader, **scan_pars)
                for cnt in counters:
                    acq_device.add_counter(cnt)
                tree.setdefault(master_acq_device, list()).append(acq_device)
            else:
                tree.setdefault(master_acq_device, list()).extend([IntegratingCounterAcquisitionDevice(cnt, **scan_pars) for cnt in counters])
        else:
            master_acq_device = master_integrating_counter.get(reader)
            if master_acq_device is None:
                master_acq_device, _ = default_master_configuration(reader, scan_pars)
                master_integrating_counter[reader] = master_acq_device
                tree.setdefault(master_acq_device, list())
            else:
                if scan_pars.get('save',False):
                    activate_master_saving(master_acq_device,True)
    return tree

def default_chain(chain, scan_pars, counters):
    count_time = scan_pars.get('count_time', 1)
    sleep_time = scan_pars.get('sleep_time')
    npoints = scan_pars.get('npoints', 1)
    
    if not counters:
        raise ValueError("No counters for scan. Hint: are all counters disabled ?")

    counters = set(counters) #eliminate duplicated counters, if any
    timer = SoftwareTimerMaster(count_time, npoints=npoints, sleep_time=sleep_time)
    
    for acq_master, acq_devices in _counters_tree(counters, scan_pars).iteritems():
        if acq_master:
            chain.add(timer, acq_master)
        else:
            acq_master = timer
        for acq_device in acq_devices:
            chain.add(acq_master, acq_device)

    chain.timer = timer
    return timer

def step_scan(chain,scan_info,name=None,save=default_writer is not None):
    scandata = scan_module.ScanSaving()
    config = scandata.get()
    root_path = config.get('root_path')
    save &= default_writer is not None
    writer = default_writer.Writer(root_path) if save else None
    scan_info['save'] = save
    scan_info['root_path'] = root_path
    scan_info['session_name'] = scandata.session
    scan_info['user_name'] = scandata.user_name
    scan_data_watch = scan_module.StepScanDataWatch(scan_info)
    return scan_module.Scan(chain,
                            name=name,
                            parent=config['parent'],
                            scan_info=scan_info,
                            writer=writer,
                            data_watch_callback=scan_data_watch)

def ascan(motor, start, stop, npoints, count_time, *counters, **kwargs):
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
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'ascan <motor> ... <count_time>']
        save (bool): save scan data to file [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): False by default
    """
    scan_info = { 'type': kwargs.get('type', 'ascan'),
                  'save': kwargs.get('save', True),
                  'title': kwargs.get('title'),
                  'sleep_time': kwargs.get('sleep_time') }

    if scan_info['title'] is None:
        args = scan_info['type'], motor.name, start, stop, npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    counters,other_counters = _get_all_counters(counters)

    # estimate scan time
    step_size = abs(stop - start) / npoints
    i_motion_t = MotionEstimation(motor, start).duration
    n_motion_t = MotionEstimation(motor, start, start + step_size).duration
    total_motion_t = i_motion_t + npoints * n_motion_t
    total_count_t = npoints * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}

    scan_info.update({ 'npoints': npoints, 'total_acq_time': total_count_t,
                       'motors': [TimestampPlaceholder(), motor], 
                       'counters': counters,
                       'other_counters': other_counters,
                       'start': [start], 'stop': [stop],
                       'count_time': count_time,
                       'estimation': estimation})

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counters + other_counters)
    top_master = LinearStepTriggerMaster(npoints,motor,start,stop)
    chain.add(top_master,timer)

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, start, stop, npoints)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","ascan"), save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan',False):
        return scan

def dscan(motor, start, stop, npoints, count_time, *counters, **kwargs):
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
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

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
                 *counters, **kwargs)
    motor.move(oldpos)
    return scan

def mesh(motor1, start1, stop1, npoints1, motor2, start2, stop2, npoints2, count_time, *counters, **kwargs):
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
    scan_info = { 'type': kwargs.get('type', 'mesh'),
                  'save': kwargs.get('save', True),
                  'title': kwargs.get('title'),
                  'sleep_time': kwargs.get('sleep_time') }

    if scan_info['title'] is None:
        args = scan_info['type'], motor1.name, start1, stop1, npoints1, \
               motor2.name, start2, stop2, npoints2, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    counters,other_counters = _get_all_counters(counters)

    # estimate scan time
    step_size1 = abs(stop1 - start1) / npoints1
    i_motion_t1 = MotionEstimation(motor1, start1).duration
    n_motion_t1 = MotionEstimation(motor1, start1, start1 + step_size1).duration
    total_motion_t1 = npoints1 *npoints2 * n_motion1_t

    step_size2 = abs(stop2 - start2) / npoints2
    i_motion_t2 = MotionEstimation(motor2, start2).duration
    n_motion_t2 = max(MotionEstimation(motor2, start2, start2 + step_size2).duration,
                      MotionEstimation(motor1, end1, start1).duration)
    total_motion_t2 = npoints2 * n_motion2_t

    imotion_t = max(i_motion_t1, i_motion_t2)

    total_motion_t = imotion_t + total_motion_t1 + total_motion_t2
    total_count_t = npoints1 * npoints2 * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}
    
    scan_info.update({ 'npoints1': npoints1, 'npoints2': npoints2, 
                       'total_acq_time': total_count_t,
                       'motors': [TimestampPlaceholder(), motor1, motor2],
                       'counters': counters,
                       'other_counters': counters,
                       'start': [start1, start2], 'stop': [stop1, stop2],
                       'count_time': count_time,
                       'estimation': estimation})

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counters + other_counters)
    top_master = MeshStepTriggerMaster(motor1, start1, stop1, npoints1,
                                       motor2, start2, stop2, npoints2)
    chain.add(top_master,timer)

    _log.info(
        "Scanning (%s, %s) from (%f, %f) to (%f, %f) in (%d, %d) points",
        motor1.name, motor2.name, start1, start2, stop1, stop2, npoints1, npoints2)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","mesh"), save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', False):
        return scan

def a2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *counters, **kwargs):
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
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

    Keyword Args:
        name (str): scan name in data nodes tree and directories [default: 'scan']
        title (str): scan title [default: 'a2scan <motor1> ... <count_time>']
        save (bool): save scan data to file [default: True]
        sleep_time (float): sleep time between 2 points [default: None]
        run (bool): if True (default), run the scan. False means just create
                    scan object and acquisition chain
        return_scan (bool): False by default
    """
    scan_info = { 'type': kwargs.get('type', 'a2scan'),
                  'save': kwargs.get('save', True),
                  'title': kwargs.get('title'),
                  'sleep_time': kwargs.get('sleep_time') }

    if scan_info['title'] is None:
        args = scan_info['type'], motor1.name, start1, stop1, \
               motor2.name, start2, stop2, npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    counters,other_counters = _get_all_counters(counters)

    # estimate scan time
    step_size1 = abs(stop1 - start1) / npoints
    i_motion1_t = MotionEstimation(motor1, start1).duration
    n_motion1_t = MotionEstimation(motor1, start1, start1 + step_size1).duration

    step_size2 = abs(stop2 - start2) / npoints
    i_motion2_t = MotionEstimation(motor2, start2).duration
    n_motion2_t = MotionEstimation(motor2, start2, start2 + step_size2).duration

    i_motion_t = max(i_motion1_t, i_motion2_t)
    n_motion_t = max(n_motion1_t, n_motion2_t)
    total_motion_t = i_motion_t + npoints * nmotion_t
    total_count_t = npoints * count_time
    estimation = {'total_motion_time': total_motion_t,
                  'total_count_time': total_count_t,
                  'total_time': total_motion_t + total_count_t}

    scan_info.update({ 'npoints': npoints, 'total_acq_time': total_count_t,
                       'motors': [TimestampPlaceholder(), motor1, motor2],
                       'counters': counters,
                       'other_counters': other_counters,
                       'start': [start1, start2], 'stop': [stop1, stop2],
                       'count_time': count_time,
                       'estimation': estimation })

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counters + other_counters)
    top_master = LinearStepTriggerMaster(npoints,
                                         motor1,start1,stop1,
                                         motor2,start2,stop2)
    chain.add(top_master,timer)

    _log.info(
        "Scanning %s from %f to %f and %s from %f to %f in %d points",
        motor1.name, start1, stop1, motor2.name, start2, stop2, npoints)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","a2scan"), save=scan_info['save'])
    
    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan',False):
        return scan


def d2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *counters, **kwargs):
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
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

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

    kwargs.setdefault('name','d2scan')

    scan = a2scan(motor1, oldpos1 + start1, oldpos1+stop1, motor2, oldpos2 + start2,
                  oldpos2 + stop2, npoints, count_time, *counters, **kwargs)

    group = Group(motor1,motor2)
    group.move(motor1,oldpos1,motor2,oldpos2)
    return scan


def timescan(count_time, *counters, **kwargs):
    """
    Time scan

    Use `timescan(..., run=False, return_scan=True)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        count_time (float): count time (seconds)
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

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
    scan_info = { 'type': kwargs.get('type', 'timescan'),
                  'save': kwargs.get('save', True),
                  'title': kwargs.get('title'),
                  'sleep_time': kwargs.get('sleep_time') ,
                  'output_mode': kwargs.get('output_mode', 'tail') }

    if scan_info['title'] is None:
        args = scan_info['type'], count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    counters,other_counters = _get_all_counters(counters)
    
    npoints = kwargs.get("npoints", 0)
    total_count_t = npoints * count_time

    scan_info.update({ 'npoints': npoints, 'total_acq_time': total_count_t,
                       'motors': [TimestampPlaceholder()], 
                       'counters': counters,
                       'other_counters': other_counters,
                       'start': [], 'stop': [], 'count_time': count_time })

    if npoints > 0:
        # estimate scan time
        estimation = {'total_motion_time': 0,
                      'total_count_time': total_count_t,
                      'total_time': total_count_t}
        scan_info['estimation'] = estimation

    _log.info("Doing %s", scan_info['type'])

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain, scan_info, counters + other_counters)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","timescan"), save=scan_info['save'])

    if kwargs.get('run', True):
        scan.run()

    if kwargs.get('return_scan', False):
        return scan


def loopscan(npoints, count_time, *counters, **kwargs):
    """
    Similar to :ref:`timescan` but npoints is mandatory

    Use `loopscan(..., run=False, return_scan=True)` to create a scan object and
    its acquisition chain without executing the actual scan.

    Args:
        npoints (int): number of points
        count_time (float): count time (seconds)
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

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
    return timescan(count_time, *counters, **kwargs)


def ct(count_time, *counters, **kwargs):
    """
    Count for a specified time

    Use `ct(..., run=False, return_scan=True)` to create a count object and
    its acquisition chain without executing the actual count.

    Note:
        This function blocks the current :class:`Greenlet`

    Args:
        count_time (float): count time (seconds)
        counters (BaseCounter or
                  MeasurementGroup): change for those counters or measurement group.
                                     if counter is empty use the active measurement group.

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

    kwargs.setdefault("name","ct")

    return timescan(count_time, *counters, **kwargs)

