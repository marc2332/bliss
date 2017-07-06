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

__all__ = ['ascan', 'a2scan', 'mesh', 'dscan', 'd2scan', 'timescan', 'ct', 'get_data']

import time
import logging
import functools
import numpy
import gevent

from bliss import setup_globals
from bliss.common.task_utils import *
from bliss.common.motor_group import Group
from bliss.common.measurement import CounterBase
from bliss.scanning.acquisition.counter import CounterAcqDevice
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning import scan as scan_module
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster, MeshStepTriggerMaster
from bliss.session import session,measurementgroup
try:
    from bliss.scanning.writer import hdf5 as default_writer
except ImportError:
    default_writer = None
from bliss.data.scan import get_data

_log = logging.getLogger('bliss.scans')

class TimestampPlaceholder:
    def __init__(self):
      self.name = 'timestamp'

def _get_counters(mg, missing_list):
    counters = list()
    if mg is not None:
        for cnt_name in mg.enable:
            cnt = setup_globals.__dict__.get(cnt_name)
            if cnt:
                counters.append(cnt)
            else:
                missing_list.append(cnt_name)
    return counters

def default_chain(chain,scan_pars,counters):
    count_time = scan_pars.get('count_time', 1)
    sleep_time = scan_pars.get('sleep_time')
    npoints = scan_pars.get('npoints', 1)
    timer = SoftwareTimerMaster(count_time, npoints=npoints, sleep_time=sleep_time)
    scan_counters = list()
    missing_counters = list()
    if counters:
        for cnt in counters:
            if isinstance(cnt, measurementgroup.MeasurementGroup):
                scan_counters.extend(_get_counters(cnt, missing_counters))
            else:
                scan_counters.append(cnt)
    else:
        scan_counters.extend(_get_counters(measurementgroup.get_active(), missing_counters))
    
    if missing_counters:
        raise ValueError("Missing counters, not in setup_globals: %s. Hint: disable inactive counters." % ", ".join(missing_counters))

    if not scan_counters:
        raise ValueError("All counters are disabled...")

    read_cnt_handler = dict()
    for cnt in set(scan_counters):
        if isinstance(cnt, CounterBase):
            try:
                read_all_handler = cnt.read_all_handler()
            except NotImplementedError:
                chain.add(timer, CounterAcqDevice(cnt, count_time=count_time, npoints=npoints))
            else:
                uniq_id = read_all_handler.id()
                cnt_acq_device = read_cnt_handler.get(uniq_id)
                if cnt_acq_device is None:
                    cnt_acq_device = CounterAcqDevice(read_all_handler, count_time=count_time, npoints=npoints)
                    chain.add(timer, cnt_acq_device)
                    read_cnt_handler[uniq_id] = cnt_acq_device
                cnt_acq_device.add_counter_to_read(cnt)
        # elif isinstance(cnt,Lima):
        #   chain.add(timer, LimaAcqDevice()))
        else:
            raise TypeError("`%r' is not a supported counter type" % repr(cnt))

    return timer

def step_scan(chain,scan_info,name=None,save=default_writer is not None):
    scandata = scan_module.ScanSaving()
    config = scandata.get()
    root_path = config.get('root_path')
    writer = default_writer.Writer(root_path) if save else None
    scan_info['root_path'] = root_path
    scan_info['session_name'] = scandata.session
    scan_info['user_name'] = scandata.user_name
    scan_data_watch = scan_module.StepScanDataWatch(root_path,scan_info)
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

    scan_info.update({ 'npoints': npoints, 'total_acq_time': npoints * count_time,
                       'motors': [TimestampPlaceholder(), motor], 'start': [start], 'stop': [stop],
                       'count_time': count_time })

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain,scan_info,counters)
    top_master = LinearStepTriggerMaster(npoints,motor,start,stop)
    chain.add(top_master,timer)

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, start, stop, npoints)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","ascan"), save=scan_info['save'])
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

    scan_info.update({ 'npoints1': npoints1, 'npoints2': npoints2, 
                       'total_acq_time': npoints1 * npoints2 * count_time,
                       'motors': [TimestampPlaceholder(), motor1, motor2],
                       'start': [start1, start2], 'stop': [stop1, stop2],
                       'count_time': count_time })

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain,scan_info,counters)
    top_master = MeshStepTriggerMaster(motor1, start1, stop1, npoints1,
                                       motor2, start2, stop2, npoints2)
    chain.add(top_master,timer)

    _log.info(
        "Scanning (%s, %s) from (%f, %f) to (%f, %f) in (%d, %d) points",
        motor1.name, motor2.name, start1, start2, stop1, stop2, npoints1, npoints2)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","mesh"), save=scan_info['save'])

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

    scan_info.update({ 'npoints': npoints, 'total_acq_time': npoints * count_time,
                       'motors': [TimestampPlaceholder(), motor1, motor2],
                       'start': [start1, start2], 'stop': [stop1, stop2],
                       'count_time': count_time })

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain,scan_info,counters)
    top_master = LinearStepTriggerMaster(npoints,
                                         motor1,start1,stop1,
                                         motor2,start2,stop2)
    chain.add(top_master,timer)

    _log.info(
        "Scanning %s from %f to %f and %s from %f to %f in %d points",
        motor1.name, start1, stop1, motor2.name, start2, stop2, npoints)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","a2scan"), save=scan_info['save'])
    
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
        return_scan (bool): False by default
    """
    scan_info = { 'type': kwargs.get('type', 'timescan'),
                  'save': kwargs.get('save', True),
                  'title': kwargs.get('title'),
                  'sleep_time': kwargs.get('sleep_time') }

    if scan_info['title'] is None:
        args = scan_info['type'], count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        scan_info['title'] = template.format(*args)

    npoints = kwargs.get("npoints", 0)
    scan_info.update({ 'npoints': npoints, 'total_acq_time': npoints * count_time,
                       'motors': [TimestampPlaceholder()], 'start': [], 'stop': [], 'count_time': count_time,
                       'total_acq_time': npoints * count_time })

    _log.info("Doing %s", scan_info['type'])

    chain = AcquisitionChain(parallel_prepare=True)
    timer = default_chain(chain,scan_info,counters)

    scan = step_scan(chain, scan_info,
                     name=kwargs.setdefault("name","timescan"), save=scan_info['save'])
    scan.run()
    return scan

def ct(count_time, *counters, **kwargs):
    """
    Count for a specified time

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
    """
    kwargs['type'] = 'ct'
    kwargs['save'] = False
    kwargs['npoints'] = 1

    kwargs.setdefault("name","ct")

    return timescan(count_time, *counters, **kwargs)

