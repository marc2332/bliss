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

__all__ = ['SCANFILE', 'set_scanfile', 'scanfile', 'last_scan_data',
           'ascan', 'a2scan', 'dscan', 'd2scan', 'timescan', 'ct']

import time
import getpass
import logging

import numpy
import gevent

from bliss.common.task_utils import *
from bliss.controllers.motor_group import Group
from .data_manager import DataManager
from .standard import get_active_counters_iter

_log = logging.getLogger('bliss.scans')


SCANFILE = "/dev/null"

def set_scanfile(filename):
    """
    Changes the active scan file.
    It supports any of the attributes of :func:`time.strftime`.
    Example::

        set_scanfile('/tmp/scans/mono_temp_%d%m%y')

    Using this format allows bliss to reinterpret the file name
    at the beginning of each scan. In the previous example, bliss
    will change files automatically between two scans that occur
    in different days.

    Args:
        filename (str): name for the new scan file
    """
    global SCANFILE
    SCANFILE = filename


def scanfile():
    """
    Returns the current active scanfile

    Returns:
        str: name of the current scan file
    """
    return time.strftime(SCANFILE)


def last_scan_data():
    """
    Returns the data corresponding to the last scan or None if no scan has
    been executed

    Returns:
        object: last scan data or None
    """
    return DataManager().last_scan_data()


def __count(counter, count_time):
    return counter.count(count_time).value


class ScanEnvironment(dict):
    """
    Internal scan environment helper.
    Used to pass the current environment between scan executor,
    the :class:`~bliss.common.data_manager.DataManager` and the
    :class:`~bliss.common.data_manager.Scan` object
    """

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.setdefault('type', 'scan')
        self.setdefault('filename', scanfile())
        self.setdefault('save', True)
        self.setdefault('data_manager', DataManager())
        self.setdefault('total_acq_time', 0)
        self.setdefault('user_name', getpass.getuser())
        if 'session_name' not in self:
            import bliss.shell
            self['session_name'] = bliss.shell.SETUP.get('session_name', 'bliss')


def ascan(motor, start, stop, npoints, count_time, *extra_counters, **kwargs):
    """
    Absolute scan

    Scans one motor, as specified by *motor*. The motor starts at the position
    given by *start* and ends at the position given by *stop*. The step size is
    `(*start*-*stop*)/(*npoints*-1)`. The number of intervals will be
    *npoints*-1. Count time is given by *count_time* (seconds).

    At the end of the scan (even in case of error) the motor will return to
    its initial position

    Args:
        motor (Axis): motor to scan
        start (float): motor start position
        stop (float): motor end position
        npoints (int): the number of points
        count_time (float): count time (seconds)
        extra_counters (BaseCounter): additional counters

    Keyword Args:
        type (str): scan type [default: 'ascan')
        title (str): scan title [default: 'ascan <motor> ... <count_time>']
        filename (str): file name [default: current value returned by \
        :func:`scanfile`]
        save (bool): save scan data to file [default: True]
        user_name (str): current user
        session_name (str): session name [default: current session name or \
        'bliss' if not inside a session]
    """
    scan_type = kwargs.setdefault('type', 'ascan')
    if 'title' not in kwargs:
        args = scan_type, motor.name, start, stop, npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        kwargs['title'] = template.format(*args)

    kwargs.setdefault('npoints', npoints)
    kwargs.setdefault('total_acq_time', npoints * count_time)

    counters = list(get_active_counters_iter()) + list(extra_counters)

    env = ScanEnvironment(kwargs, count_time=count_time)
    dm = env['data_manager']

    _log.info("Scanning %s from %f to %f in %d points",
              motor.name, start, stop, npoints)

    motors = [motor]
    scan = dm.new_scan(motors, npoints, counters, env)

    start_pos = motor.position()

    def scan_cleanup():
        print "Returning motor %s to %f" % (motor.name, start_pos)
        motor.move(start_pos)

    motor.move(start)
    ipoint = 0
    countlabellen = len("{0:d}".format(npoints))
    countformatstr = "{0:" + "{0:d}".format(countlabellen) + "d}"

    with cleanup(scan.end):
      with error_cleanup(scan_cleanup):
        for position in numpy.linspace(start, stop, npoints):
            ipoint = ipoint + 1
            countlabel = "(" + "{0:3d}".format(
                ipoint) + "/" + "{0:3d}".format(npoints) + ")"
            countlabel = "(" + countformatstr.format(
                ipoint) + "/" + countformatstr.format(npoints) + ")"
            motor.move(float(position))

            acquisitions = []
            values = [position]
            for counter in counters:
                acquisitions.append(gevent.spawn(__count, counter, count_time))

            gevent.joinall(acquisitions)

            values.extend([a.get() for a in acquisitions])
            # print values
            scan.add(values)


def dscan(motor, start, stop, npoints, count_time, *extra_counters, **kwargs):
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
        extra_counters (BaseCounter): additional counters

    Keyword Args:
        type (str): scan type [default: 'ascan')
        title (str): scan title [default: 'dscan <motor> ... <count_time>']
        filename (str): file name [default: current value returned by \
        :func:`scanfile`]
        save (bool): save scan data to file [default: True]
        user_name (str): current user
        session_name (str): session name [default: current session name or \
        'bliss' if not inside a session]
    """
    kwargs.setdefault('type', 'dscan')
    oldpos = motor.position()
    ascan(motor, oldpos + start, oldpos + stop, npoints, count_time,
          *extra_counters, **kwargs)
    motor.move(oldpos)


def a2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *extra_counters, **kwargs):
    """
    Absolute 2 motor scan

    Scans two motors, as specified by *motor1* and *motor2*. The motors start
    at the positions given by *start1* and *start2* and end at the positions
    given by *stop1* and *stop2*. The step size for each motor is given by
    `(*start*-*stop*)/(*npoints*-1)`. The number of intervals will be
    *npoints*-1. Count time is given by *count_time* (seconds).

    At the end of the scan (even in case of error) the motors will return to
    its initial positions

    Args:
        motor1 (Axis): motor1 to scan
        start1 (float): motor1 start position
        stop1 (float): motor1 end position
        motor2 (Axis): motor2 to scan
        start2 (float): motor2 start position
        stop2 (float): motor2 end position
        npoints (int): the number of points
        count_time (float): count time (seconds)
        extra_counters (BaseCounter): additional counters

    Keyword Args:
        type (str): scan type [default: 'a2scan')
        title (str): scan title [default: 'a2scan <motor1> ... <count_time>']
        filename (str): file name [default: current value returned by \
        :func:`scanfile`]
        save (bool): save scan data to file [default: True]
        user_name (str): current user
        session_name (str): session name [default: current session name or \
        'bliss' if not inside a session]
    """
    scan_type = kwargs.setdefault('type', 'a2scan')
    if 'title' not in kwargs:
        args = scan_type, motor1.name, start1, stop1, \
               motor2.name, start2, stop2, npoints, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        kwargs['title'] = template.format(*args)

    kwargs.setdefault('npoints', npoints)
    kwargs.setdefault('total_acq_time', npoints * count_time)

    counters = list(get_active_counters_iter()) + list(extra_counters)

    env = ScanEnvironment(kwargs, count_time=count_time)
    dm = env['data_manager']

    _log.info(
        "Scanning %s from %f to %f and %s from %f to %f in %d points",
        motor1.name, start1, stop1, motor2.name, start2, stop2, npoints)

    motors = [motor1, motor2]
    scan = dm.new_scan(motors, npoints, counters, env)
    start_pos1 = motor1.position()
    start_pos2 = motor2.position()
    motor_group = Group(motor1, motor2)

    def scan_cleanup():
        _log.info(
            "Returning motor %s to %f and motor %s to %f",
            motor1.name, start_pos1, motor2.name, start_pos2)
        motor_group.move(motor1, start_pos1, motor2, start_pos2)

    motor_group.move(motor1, start1, motor2, start2)
    ipoint = 0
    countlabellen = len("{0:d}".format(npoints))
    countformatstr = "{0:" + "{0:d}".format(countlabellen) + "d}"

    s1 = numpy.linspace(start1, stop1, npoints)
    s2 = numpy.linspace(start2, stop2, npoints)
    with cleanup(scan.end):
      with error_cleanup(scan_cleanup):
        for ii in range(npoints):
            ipoint = ipoint + 1
            motor_group.move(motor1, s1[ii], motor2, s2[ii])

            acquisitions = []
            values = [m.position() for m in (motor1, motor2)]
            for counter in counters:
                acquisitions.append(gevent.spawn(__count, counter, count_time))

            gevent.joinall(acquisitions)
            values.extend([a.get() for a in acquisitions])
            # print values
            scan.add(values)

def d2scan(motor1, start1, stop1, motor2, start2, stop2, npoints, count_time,
           *extra_counters, **kwargs):
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
        extra_counters (BaseCounter): additional counters

    Keyword Args:
        type (str): scan type [default: 'ascan')
        title (str): scan title [default: 'd2scan <motor1> ... <count_time>']
        filename (str): file name [default: current value returned by \
        :func:`scanfile`]
        save (bool): save scan data to file [default: True]
        user_name (str): current user
        session_name (str): session name [default: current session name or \
        'bliss' if not inside a session]
    """
    kwargs.setdefault('type', 'd2scan')

    oldpos1 = motor1.position()
    oldpos2 = motor2.position()

    counters = list(get_active_counters_iter()) + list(extra_counters)

    a2scan(motor1, oldpos1 + start1, oldpos1+stop1, motor2, oldpos2 + start2,
           oldpos2 + stop2, npoints, count_time, *counters, **kwargs)

    motor1.move(oldpos1)
    motor2.move(oldpos2)


def timescan(count_time, *extra_counters, **kwargs):
    """
    Time scan

    Args:
        count_time (float): count time (seconds)
        extra_counters (BaseCounter): additional counters

    Keyword Args:
        sleep_time (float): sleep time (seconds) [default: 0]
        type (str): scan type [default: 'ascan')
        title (str): scan title [default: 'timescan <count_time>']
        filename (str): file name [default: current value returned by \
        :func:`scanfile`]
        save (bool): save scan data to file [default: True]
        user_name (str): current user
        session_name (str): session name [default: current session name or \
        'bliss' if not inside a session]
    """
    scan_type = kwargs.setdefault('type', 'timescan')
    if 'title' not in kwargs:
        args = scan_type, count_time
        template = " ".join(['{{{0}}}'.format(i) for i in range(len(args))])
        kwargs['title'] = template.format(*args)

    sleep_time = kwargs.setdefault("sleep_time", 0)
    npoints = kwargs.setdefault("npoints", 0)

    if npoints > 0:
        kwargs['total_acq_time'] = npoints * (count_time + sleep_time)

    counters = list(get_active_counters_iter()) + list(extra_counters)

    env = ScanEnvironment(kwargs, count_time=count_time)
    dm = env['data_manager']

    if max(count_time, sleep_time) == 0:
        raise RuntimeError("Either sleep or count time has to be specified.")

    _log.info("Doing %s", scan_type)

    scan = dm.new_timescan(counters, env)

    t0 = time.time()
    with cleanup(scan.end):
        while True:
            acquisitions = []
            tt = time.time() - t0
            values = [tt]
            for counter in counters:
                acquisitions.append(gevent.spawn(__count, counter, count_time))

            gevent.joinall(acquisitions)

            values.extend([a.get() for a in acquisitions])
            scan.add(values)
            npoints -= 1
            if npoints == 0:
                break
            time.sleep(sleep_time)


def ct(count_time, *counters, **kwargs):
    """
    Count for a specified time

    Note:
        This function blocks the current :class:`Greenlet`

    Args:
        count_time (float): count time (seconds)
        extra_counters (BaseCounter): additional counters

    Keyword Args:
        sleep_time (float): sleep time (seconds) [default: 0]
        type (str): scan type [default: 'ascan')
        title (str): scan title [default: 'ct <count_time>']
        filename (str): file name [default: current value returned by \
        :func:`scanfile`]
        save (bool): save scan data to file [default: True]
        user_name (str): current user
        session_name (str): session name [default: current session name or \
        'bliss' if not inside a session]
    """
    kwargs.setdefault('type', 'ct')
    kwargs.setdefault('save', False)
    kwargs['npoints'] = 1
    return timescan(count_time, *counters, **kwargs)

