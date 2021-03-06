# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

import numpy
import pytest
import gevent
from unittest import mock

from bliss.common import event
from bliss.common import scans
from bliss.scanning.scan import Scan, ScanState
from bliss.scanning.chain import AcquisitionChain, AcquisitionSlave
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.common.scans import DEFAULT_CHAIN


class DebugMotorMockupAcquisitionSlave(AcquisitionSlave):
    def __init__(self, name, motor_mockup):
        super().__init__(motor_mockup, name=name)
        self.motor_mockup = motor_mockup
        self.channels.append(AcquisitionChannel(name + "_pos", float, ()))
        self.channels.append(AcquisitionChannel(name + "_time", float, ()))

    def set_time_ref(self, state):
        if "MOVING" in state:
            self.time_ref = time.time()

    def prepare(self):
        pass

    def start(self):
        event.connect(self.motor_mockup, "internal_state", self.set_time_ref)

    def stop(self):
        event.disconnect(self.motor_mockup, "internal_state", self.set_time_ref)

    def trigger(self):
        controller = self.motor_mockup.controller
        motion = controller._axis_moves[self.motor_mockup]["motion"]
        steps = motion.trajectory.position()
        value = steps / float(self.motor_mockup.steps_per_unit)
        self.channels.update(
            {
                self.name + "_pos": value,
                self.name + "_time": time.time() - self.time_ref,
            }
        )


def test_software_position_trigger_master(session):
    robz = session.config.get("robz")
    robz.velocity = 10
    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(robz, 0, 1, 5),
        DebugMotorMockupAcquisitionSlave("debug", robz),
    )
    # Run scan
    s = Scan(chain, save=False)
    with gevent.Timeout(5):
        s.run()
    # Check data
    data = s.get_data()

    # results are hazardous on CI :(
    # should work on real computers.
    pytest.xfail()

    # Typical position error is +0.025 in position unit
    # That's because of redis + gevent delays (~2.5 ms)
    assert len(data["robz"]) == 5
    assert data["robz"] == pytest.approx(data["debug_pos"], abs=1.0)
    expected_triggers = [0.034, 0.054, 0.074, 0.09, 0.11]
    assert len(data["debug_time"]) == 5
    assert data["debug_time"] == pytest.approx(expected_triggers, abs=0.02)


def test_iter_software_position_trigger_master(session):
    robz = session.config.get("robz")
    robz.velocity = 100
    chain = AcquisitionChain()
    start_pos = [0, 12, 24]
    end_pos = 30
    master = SoftwarePositionTriggerMaster(robz, start_pos, end_pos, 10, time=0.5)
    device = DebugMotorMockupAcquisitionSlave("debug", robz)
    chain.add(master, device)
    s = Scan(chain, save=False)
    with gevent.Timeout(10):
        s.run()

    data = s.get_data()
    assert len(data["robz"]) == 25

    assert data["robz"] == pytest.approx(
        data["debug_pos"], abs=((end_pos - start_pos[0]) / 10) * 0.5
    )
    error = numpy.abs(data["robz"] - data["debug_pos"])
    assert numpy.median(error) < 0.1, error

    assert len(data["debug_time"]) == len(data["robz"])
    assert list(master._positions) == list(
        numpy.linspace(24, 30, master._SoftwarePositionTriggerMaster__last_npoints + 1)[
            :-1
        ]
    )


def test_multi_top_master(session, diode_acq_device_factory, diode):
    mot = session.config.get("m0")
    start, stop, npoints, count_time = (0, 1, 20, 1)
    chain = AcquisitionChain(parallel_prepare=True)
    master = SoftwarePositionTriggerMaster(mot, start, stop, npoints, time=count_time)
    count_time = (float(count_time) / npoints) / 2.0
    if count_time < 0:
        count_time = 0
    timer = SoftwareTimerMaster(count_time, name="fast", npoints=npoints)
    chain.add(master, timer)

    acquisition_device, diode1 = diode_acq_device_factory.get(
        count_time=count_time, npoints=npoints
    )
    diode2 = diode
    chain.add(timer, acquisition_device)

    scan_params = {"npoints": 0, "count_time": count_time * 2.0}
    chain.append(DEFAULT_CHAIN.get(scan_params, (diode2,)))

    scan = Scan(chain, name="multi_master", save=False)
    scan.run()

    # Check that there are twice more stored values for diode2 than for diode1.
    val1 = len(diode2.store_values) - len(diode1.store_values)
    val2 = len(diode2.store_values) / 2

    # Time is strange in CI. let's take a 20% margin...
    assert pytest.approx(val1, rel=0.2) == val2


def test_interrupted_scan(session, diode_acq_device_factory):
    robz = session.config.get("robz")
    robz.velocity_low_limit = 1
    robz.velocity = 1
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=5)
    acquisition_device_2, _ = diode_acq_device_factory.get(count_time=0.1, npoints=5)
    master = SoftwarePositionTriggerMaster(robz, 0, 1, 5)
    chain.add(master, acquisition_device_1)
    chain.add(master, acquisition_device_2)
    # Run scan
    s = Scan(chain, save=False)
    scan_task = gevent.spawn(s.run)

    with gevent.Timeout(1):
        s.wait_state(ScanState.STARTING)

    try:
        scan_task.kill(KeyboardInterrupt)
    except:
        assert scan_task.ready()

    assert s.state == ScanState.USER_ABORTED
    assert acquisition_device_1.stop_flag
    assert acquisition_device_2.stop_flag


def test_timeout_error(session, diode_acq_device_factory):
    robz = session.config.get("robz")
    robz.velocity_limits = 0, 100
    robz.velocity = 1
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=5)
    acquisition_device_2, _ = diode_acq_device_factory.get(count_time=0.1, npoints=5)
    master = SoftwarePositionTriggerMaster(robz, 0, 1, 5)
    chain.add(master, acquisition_device_1)
    chain.add(master, acquisition_device_2)
    s = Scan(chain, save=False)

    with mock.patch.object(robz, "stop", side_effect=gevent.Timeout) as stop_method:
        with mock.patch.object(
            acquisition_device_1, "stop", side_effect=gevent.Timeout
        ) as acq_dev_stop_method:
            # Run scan
            scan_task = gevent.spawn(s.run)

            with gevent.Timeout(1):
                s.wait_state(ScanState.STARTING)

            gevent.sleep(0.2)

            try:
                scan_task.kill(KeyboardInterrupt)
            except:
                assert scan_task.ready()

    assert stop_method.called_once
    assert acq_dev_stop_method.called_once
    assert acquisition_device_2.stop_flag


def test_scan_too_fast(session, diode_acq_device_factory):
    robz = session.config.get("robz")
    robz.velocity = 10
    chain = AcquisitionChain()
    acquisition_device_1, _ = diode_acq_device_factory.get(count_time=0.1, npoints=5)
    master = SoftwarePositionTriggerMaster(robz, 0, 1, 5)
    chain.add(master, acquisition_device_1)
    s = Scan(chain, save=False)
    with gevent.Timeout(6):
        with pytest.raises(RuntimeError) as e_info:
            # aborted due to bad triggering on slaves
            s.run()
        assert "Aborted due to" in str(e_info.value)


def test_scan_failure(session, diode_acq_device_factory):
    robz = session.config.get("robz")
    robz.velocity_low_limit = 1
    robz.velocity = 2
    chain = AcquisitionChain()
    acquisition_device_1, diode1 = diode_acq_device_factory.get(
        count_time=0.1, npoints=5, trigger_fail=True
    )
    acquisition_device_2, diode2 = diode_acq_device_factory.get(
        count_time=0.1, npoints=5
    )
    master = SoftwarePositionTriggerMaster(robz, 0, 1, 5)
    chain.add(master, acquisition_device_1)
    chain.add(master, acquisition_device_2)

    # Run scan
    s = Scan(chain, save=False)
    with pytest.raises(RuntimeError) as e_info:
        s.run()

    # make sure it is really our exception, not something else
    assert str(e_info.value) == "Trigger failure"
    assert len(diode1.store_values) == 0
    assert acquisition_device_1.stop_flag
    assert acquisition_device_2.stop_flag
    assert (
        pytest.approx(acquisition_device_1.stop_time, abs=1e-2)
        == acquisition_device_2.stop_time
    )
