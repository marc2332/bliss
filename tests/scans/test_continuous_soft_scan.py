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
