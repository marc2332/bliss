# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""
Required hardware: P201 card installed in lid00c
Required software: Running bliss-ct2-server on tcp::/lid00c:8909

To change PC replace in `../test-configuration/ct2.yml` the address
of the P201 card
"""

import time
import contextlib

import numpy
import pytest
import zerorpc

from gevent import sleep, spawn
from gevent.event import Event

from bliss.common.event import dispatcher
from bliss.controllers.ct2.device import AcqMode, AcqStatus, StatusSignal


TEN_KHz = 10000
ERROR_MARGIN = 10E-2   # 100ms


class EventReceiver(object):
    """Context manager which accumulates data"""
    def __init__(self, device):
        self.device = device
        self.finish = Event()
        self.events = []

    def __call__(self, value, signal):
        self.events.append((time.time(), signal, value))
        if signal == StatusSignal:
            if value == AcqStatus.Running:
                self.start = time.time()
            elif value == AcqStatus.Ready:
                self.end = time.time()
                self.finish.set()

    def __enter__(self):
        dispatcher.connect(self, sender=self.device)
        return self

    def __exit__(self, *args):
        dispatcher.disconnect(self, sender=self.device)


@pytest.fixture(params=[1, 10, 100], ids=['1 point', '10 points', '100 points'])
def device(request, beacon):
    """
    Requirements to run this fixture:

    hardware: P201 card installed in lid00c
    software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    beacon.reload()
    device = beacon.get('p201')
    device.timer_freq = 12.5E6
    device.acq_nb_points = request.param
    yield device
    device.close()


def data_tests(device, expected_data):
    expected_nb_points = len(expected_data)

    # get all data (does not consume it)
    data = device.get_data()
    assert data == pytest.approx(expected_data)

    from_index = 3
    if expected_nb_points > from_index:
        # get data from point nb 3
        data_from_3 = device.get_data(3)
        assert (data[3:] == data_from_3).all()

    # read data: consumes it. Next calls will get no data
    data_consume = device.read_data()

    assert (data == data_consume).all()

    data_empty = device.get_data()

    assert data_empty.size == 0


def soft_trigger_points(device, n, period):
    i, start = 0, time.time()
    while i < n:
        sleep((start + (i+1)*period) - time.time())
        device.trigger_point()
        i += 1


def test_internal_trigger_single_wrong_config(device):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    device.acq_mode = AcqMode.IntTrigSingle
    device.acq_expo_time = 1
    device.acq_point_period = None

    # Should not be able to prepare internal trigger single without
    # a point period
    with pytest.raises(zerorpc.RemoteError):
        device.prepare_acq()


def test_internal_trigger_single(device):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    expo_time = 0.02
    point_period = expo_time + 0.01
    freq = device.timer_freq
    nb_points = device.acq_nb_points
    device.acq_mode = AcqMode.IntTrigSingle
    device.acq_expo_time = expo_time
    device.acq_point_period = point_period
    device.acq_channels = 3,

    with EventReceiver(device) as receiver:
        device.prepare_acq()
        device.start_acq()
        receiver.finish.wait()

    elapsed = receiver.end - receiver.start
    expected_elapsed = nb_points * point_period
    assert elapsed == pytest.approx(expected_elapsed, abs=ERROR_MARGIN)

    timer_ticks = int(freq * expo_time)
    ch_3_value = int(TEN_KHz * expo_time)
    expected_data = numpy.array([(ch_3_value, timer_ticks, i)
                                 for i in range(nb_points)])
    data_tests(device, expected_data)


def test_internal_trigger_single_stop_acq(device):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    expo_time = 0.02
    point_period = expo_time + 0.01
    freq = device.timer_freq
    nb_points = device.acq_nb_points
    device.acq_mode = AcqMode.IntTrigSingle
    device.acq_expo_time = expo_time
    device.acq_point_period = point_period
    device.acq_channels = 3,

    expected_elapsed = nb_points * point_period

    with EventReceiver(device) as receiver:
        device.prepare_acq()
        device.start_acq()
        # stop around 10%
        sleep(0.1 * expected_elapsed)
        device.stop_acq()
        start_stop = time.time()
        receiver.finish.wait()
        end_stop = time.time()
        assert (end_stop - start_stop) < 10E-3  # allow 10ms for stop


def test_internal_trigger_multi_wrong_config(device):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    device.acq_mode = AcqMode.IntTrigMulti
    device.acq_expo_time = 1
    device.acq_point_period = 1.1
    device.acq_nb_points = 1

    # Should not be able to prepare internal trigger multi with a point period
    with pytest.raises(zerorpc.RemoteError):
        device.prepare_acq()


def test_internal_trigger_multi(device):
    """
    Required hardware: Only P201 card is required
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    expo_time = 0.02
    soft_point_period = expo_time + 0.01
    freq = device.timer_freq
    nb_points = device.acq_nb_points
    device.acq_mode = AcqMode.IntTrigMulti
    device.acq_expo_time = expo_time
    device.acq_point_period = None
    device.acq_channels = 3,
    nb_triggers = nb_points - 1

    with EventReceiver(device) as receiver:
        device.prepare_acq()
        device.start_acq()
        trigger_task = spawn(soft_trigger_points, device,
                             nb_triggers, soft_point_period)
        receiver.finish.wait()

    assert trigger_task.ready()
    assert trigger_task.exception == None

    elapsed = receiver.end - receiver.start
    expected_elapsed = (nb_points - 1) * soft_point_period + 1 * expo_time
    assert elapsed == pytest.approx(expected_elapsed, abs=ERROR_MARGIN)

    timer_ticks = int(freq * expo_time)
    ch_3_value = int(TEN_KHz * expo_time)
    expected_data = numpy.array([(ch_3_value, timer_ticks, i)
                                 for i in range(nb_points)])
    data_tests(device, expected_data)


def test_software_trigger_readout_wrong_config(device):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    device.acq_mode = AcqMode.SoftTrigReadout
    device.acq_expo_time = None
    device.acq_point_period = 1.1

    # Should not be able to prepare soft trigger readout with point period
    with pytest.raises(zerorpc.RemoteError):
        device.prepare_acq()


def test_software_trigger_readout(device):
    expo_time = None
    soft_point_period = 0.11
    freq = device.timer_freq
    nb_points = device.acq_nb_points
    device.acq_mode = AcqMode.SoftTrigReadout
    device.acq_expo_time = expo_time
    device.acq_point_period = None
    device.acq_channels = 3,
    nb_triggers = nb_points

    with EventReceiver(device) as receiver:
        device.prepare_acq()
        device.start_acq()
        trigger_task = spawn(soft_trigger_points, device,
                             nb_triggers, soft_point_period)
        receiver.finish.wait()

    assert trigger_task.ready()
    assert trigger_task.exception == None

    elapsed = receiver.end - receiver.start
    expected_elapsed = nb_points * soft_point_period
    assert elapsed == pytest.approx(expected_elapsed, abs=ERROR_MARGIN)

    timer_ticks = int(freq * soft_point_period)
    ch_3_value = int(TEN_KHz * soft_point_period)
    expected_data = numpy.array([(ch_3_value, timer_ticks, i)
                                 for i in range(nb_points)])
    data_tests(device, expected_data)
