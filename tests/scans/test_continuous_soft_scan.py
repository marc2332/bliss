# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import gevent

from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster


class DebugMotorMockupAcquisitionDevice(AcquisitionDevice):
    def __init__(self, name, motor_mockup):
        super(DebugMotorMockupAcquisitionDevice, self).__init__(
            motor_mockup, name)
        self.motor_mockup = motor_mockup
        self.channels.append(
            AcquisitionChannel(self.name, float, ()))

    def trigger(self):
        controller = self.motor_mockup.controller
        motion = controller._axis_moves[self.motor_mockup]['motion']
        steps = motion.trajectory.position()
        value = steps / float(self.motor_mockup.steps_per_unit)
        self.channels.update({self.name: value})

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass


def test_software_position_trigger_master(beacon):
    roby = beacon.get('roby')
    roby.velocity(10)
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(roby, 0, 1, 5),
              DebugMotorMockupAcquisitionDevice('debug', roby))
    # Run scan
    s = Scan(chain)
    with gevent.Timeout(5):
        s.run()
    # Check data
    data = scans.get_data(s)
    # Typical position error is +0.025 in position unit
    # That's because of redis + gevent delays (~0.0025 ms)
    assert data['roby'] == pytest.approx(data['debug'], abs=0.05)
