# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""P201 hardware tests

* For now only tests that don't require external trigger
* Need a P201 card installed on the PC where tests are run

Run with:

    $ pytest -c /dev/null tests/controllers_hw/test_ct2_acq.py -v \
    --cov bliss.controllers.ct2 --cov-report html --cov-report term

"""

import time
import contextlib

import numpy
import pytest

from gevent import sleep, spawn
from gevent.event import Event

import subprocess
from bliss.common.event import dispatcher
from bliss.controllers.ct2.client import create_and_configure_device
from bliss.controllers.ct2.device import AcqMode, AcqStatus, StatusSignal


CT2_PORT = 9909
TEN_KHz = 10000
ERROR_MARGIN = 10E-3  # 10ms
MIN_HARD_EXPO_TIME = 10e-6  # 10 us


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


@pytest.fixture(
    params=[1, 30, 853, 9293, 563859],
    ids=["1 point", "30 points", "853 points", "9_293 points", "563_859 points"],
)
def ct2(request):
    address = request.config.getoption("--ct2")
    port = str(CT2_PORT)
    tcp_address = "tcp://localhost:" + port
    args = ["bliss-ct2-server", "--address=" + address, "--port=" + port]
    proc = subprocess.Popen(args)
    time.sleep(0.5)  # wait for bliss-ct2-server to be ready
    assert proc.returncode is None
    cfg = {
        "name": "p201_01",
        "class": "CT2",
        "type": "P201",
        "address": tcp_address,
        "timer": dict(counter_name="sec"),
        "channels": [
            dict(counter_name="mon", address=3),
            dict(counter_name="det", address=5),
            dict(counter_name="apd", address=6),
        ],
    }
    try:
        p201 = create_and_configure_device(cfg)
        try:
            p201.acq_nb_points = request.param
            yield p201
        finally:
            p201.close()
    finally:
        proc.terminate()


def data_tests(ct2, expected_data):
    expected_nb_points = len(expected_data)

    # get all data (does not consume it)
    data = ct2.get_data()
    assert pytest.approx(data, expected_data)

    from_index = 3
    if expected_nb_points > from_index:
        # get data from point nb 3
        data_from_3 = ct2.get_data(3)
        assert (data[3:] == data_from_3).all()

    # read data: consumes it. Next calls will get no data
    data_consume = ct2.read_data()

    assert (data == data_consume).all()

    data_empty = ct2.get_data()

    assert data_empty.size == 0


def soft_trigger_points(ct2, n, period):
    i, start = 0, time.time()
    while i < n:
        sleep((start + (i + 1) * period) - time.time())
        ct2.trigger_point()
        i += 1


def test_internal_trigger_single_wrong_config(ct2):
    """
    Required hardware: P201 card installed in local PC
    """
    ct2.acq_mode = AcqMode.IntTrigSingle
    ct2.acq_expo_time = 1
    ct2.acq_point_period = None

    # Should not be able to prepare internal trigger single without
    # a point period
    with pytest.raises(Exception):
        ct2.prepare_acq()


def test_internal_trigger_single(ct2):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    nb_points = ct2.acq_nb_points
    expo_time = max(MIN_HARD_EXPO_TIME, .02 / nb_points)
    point_period = expo_time * 1.1
    freq = ct2.timer_freq
    ct2.acq_mode = AcqMode.IntTrigSingle
    ct2.acq_expo_time = expo_time
    ct2.acq_point_period = point_period
    ct2.acq_channels = (3,)

    with EventReceiver(ct2) as receiver:
        ct2.prepare_acq()
        ct2.start_acq()
        receiver.finish.wait()

    elapsed = receiver.end - receiver.start
    expected_elapsed = nb_points * point_period
    error = ERROR_MARGIN + 1e-6 * nb_points  # 1us per point
    assert elapsed == pytest.approx(expected_elapsed, abs=error)

    timer_ticks = int(freq * expo_time)
    ch_3_value = int(TEN_KHz * expo_time)
    expected_data = numpy.array(
        [(ch_3_value, timer_ticks, i) for i in range(nb_points)]
    )
    data_tests(ct2, expected_data)


def test_internal_trigger_single_stop_acq(ct2):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    nb_points = ct2.acq_nb_points
    expo_time = max(100e-6, .02 / nb_points)
    point_period = expo_time * 1.1
    freq = ct2.timer_freq
    ct2.acq_mode = AcqMode.IntTrigSingle
    ct2.acq_expo_time = expo_time
    ct2.acq_point_period = point_period
    ct2.acq_channels = (3,)

    expected_elapsed = nb_points * point_period

    with EventReceiver(ct2) as receiver:
        ct2.prepare_acq()
        ct2.start_acq()
        # stop around 10% or 1s
        sleep(min(0.1 * expected_elapsed, 1))
        ct2.stop_acq()
        start_stop = time.time()
        receiver.finish.wait()
        end_stop = time.time()
        assert (end_stop - start_stop) < 10E-3  # allow 10ms for stop


def test_internal_trigger_multi_wrong_config(ct2):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    ct2.acq_mode = AcqMode.IntTrigMulti
    ct2.acq_expo_time = 1
    ct2.acq_point_period = 1.1
    ct2.acq_nb_points = 1

    # Should not be able to prepare internal trigger multi with a point period
    with pytest.raises(Exception):
        ct2.prepare_acq()


def test_internal_trigger_multi(ct2):
    """
    Required hardware: Only P201 card is required
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    nb_points = ct2.acq_nb_points
    if nb_points > 1000:
        pytest.skip("would take too long")
    expo_time = max(MIN_HARD_EXPO_TIME, .02 / nb_points)
    soft_point_period = expo_time + 0.01
    freq = ct2.timer_freq
    ct2.acq_mode = AcqMode.IntTrigMulti
    ct2.acq_expo_time = expo_time
    ct2.acq_point_period = None
    ct2.acq_channels = (3,)
    nb_triggers = nb_points - 1

    with EventReceiver(ct2) as receiver:
        ct2.prepare_acq()
        ct2.start_acq()
        trigger_task = spawn(soft_trigger_points, ct2, nb_triggers, soft_point_period)
        receiver.finish.wait()

    assert trigger_task.ready()
    assert trigger_task.exception == None

    elapsed = receiver.end - receiver.start
    expected_elapsed = (nb_points - 1) * soft_point_period + 1 * expo_time
    error = ERROR_MARGIN + 1e-6 * nb_points  # 1us per point
    assert elapsed == pytest.approx(expected_elapsed, abs=error)

    timer_ticks = int(freq * expo_time)
    ch_3_value = int(TEN_KHz * expo_time)
    expected_data = numpy.array(
        [(ch_3_value, timer_ticks, i) for i in range(nb_points)]
    )
    data_tests(ct2, expected_data)


def test_software_trigger_readout_wrong_config(ct2):
    """
    Required hardware: P201 card installed in lid00c
    Required software: Running bliss-ct2-server on tcp::/lid00c:8909
    """
    ct2.acq_mode = AcqMode.SoftTrigReadout
    ct2.acq_expo_time = None
    ct2.acq_point_period = 1.1

    # Should not be able to prepare soft trigger readout with point period
    with pytest.raises(Exception):
        ct2.prepare_acq()


def test_software_trigger_readout(ct2):
    nb_points = ct2.acq_nb_points
    if nb_points > 1000:
        pytest.skip("would take too long")
    expo_time = None
    soft_point_period = max(10e-3, .02 / nb_points)
    freq = ct2.timer_freq
    nb_points = ct2.acq_nb_points
    ct2.acq_mode = AcqMode.SoftTrigReadout
    ct2.acq_expo_time = expo_time
    ct2.acq_point_period = None
    ct2.acq_channels = (3,)
    nb_triggers = nb_points

    with EventReceiver(ct2) as receiver:
        ct2.prepare_acq()
        ct2.start_acq()
        trigger_task = spawn(soft_trigger_points, ct2, nb_triggers, soft_point_period)
        receiver.finish.wait()

    assert trigger_task.ready()
    assert trigger_task.exception == None

    elapsed = receiver.end - receiver.start
    expected_elapsed = nb_points * soft_point_period
    assert elapsed == pytest.approx(expected_elapsed, abs=ERROR_MARGIN)

    timer_ticks = int(freq * soft_point_period)
    ch_3_value = int(TEN_KHz * soft_point_period)
    expected_data = numpy.array(
        [(ch_3_value, timer_ticks, i) for i in range(nb_points)]
    )
    data_tests(ct2, expected_data)
