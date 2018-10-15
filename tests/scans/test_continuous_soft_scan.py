# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

import pytest
import gevent

from bliss.common import event
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.timer import SoftwareTimerMaster
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.controllers.simulation_diode import SimulationDiodeSamplingCounter
from bliss.common.scans import DEFAULT_CHAIN


class DebugMotorMockupAcquisitionDevice(AcquisitionDevice):
    def __init__(self, name, motor_mockup):
        super(DebugMotorMockupAcquisitionDevice, self).__init__(motor_mockup, name)
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


def test_software_position_trigger_master(beacon):
    roby = beacon.get("roby")
    roby.velocity(10)
    chain = AcquisitionChain()
    chain.add(
        SoftwarePositionTriggerMaster(roby, 0, 1, 5),
        DebugMotorMockupAcquisitionDevice("debug", roby),
    )
    # Run scan
    s = Scan(chain, writer=None)
    with gevent.Timeout(5):
        s.run()
    # Check data
    data = s.get_data()
    # Typical position error is +0.025 in position unit
    # That's because of redis + gevent delays (~2.5 ms)
    expected_triggers = [0.01, 0.03, 0.05, 0.07, 0.09]
    assert data["roby"] == pytest.approx(data["debug_pos"], abs=0.2)
    assert data["debug_time"] == pytest.approx(expected_triggers, abs=0.02)


def test_multi_top_master(beacon):

    # This test is failing at the moment and should be investigated.
    # Some greenlets are still running at the end of the test.
    pytest.xfail()

    class Simu(SimulationDiodeSamplingCounter):
        def __init__(self, *args, **kwargs):
            SimulationDiodeSamplingCounter.__init__(self, *args, **kwargs)
            self.store_time = list()
            self.store_values = list()

        def read(self, *args, **kwargs):
            self.store_time.append(time.time())
            value = SimulationDiodeSamplingCounter.read(self, *args, **kwargs)
            self.store_values.append(value)
            return value

    mot = beacon.get("m0")
    start, stop, npoints, count_time = (0, 1, 100, 2)
    chain = AcquisitionChain(parallel_prepare=True)
    master = SoftwarePositionTriggerMaster(mot, start, stop, npoints, time=count_time)
    count_time = (float(count_time) / npoints) - 10e-3
    if count_time < 0:
        count_time = 0
    timer = SoftwareTimerMaster(count_time, name="fast", npoints=npoints)
    chain.add(master, timer)

    diode2 = Simu("diode2", None)
    acquisition_device = SamplingCounterAcquisitionDevice(
        diode2, count_time=count_time, npoints=npoints
    )
    chain.add(timer, acquisition_device)

    diode1 = Simu("diode1", None)
    scan_params = {"npoints": 0, "count_time": count_time * 2.}
    chain.append(DEFAULT_CHAIN.get(scan_params, (diode2,)))

    scan = Scan(chain, name="multi_master", writer=None)
    scan.run()
    # should be about the same sampling rate
    # just to test that both top master run in parallel
    assert pytest.approx(
        len(diode2.store_values) - len(diode1.store_values),
        len(diode2.store_values) * 0.1,
    )
