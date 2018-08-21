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
from bliss.scanning.acquisition.motor import SweepMotorMaster


class DebugMotorMockupPositionAcquisitionDevice(AcquisitionDevice):
    def __init__(self, name, motor_mockup):
        super(DebugMotorMockupPositionAcquisitionDevice, self).__init__(
            motor_mockup, name, prepare_once=True, start_once=True
        )
        self.motor_mockup = motor_mockup
        self.channels.append(AcquisitionChannel(name + "_pos", float, ()))
        self.channels.append(AcquisitionChannel(name + "_time", float, ()))
        self._start_time = None

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def trigger(self):
        controller = self.motor_mockup.controller
        value = self.motor_mockup.position()
        if self._start_time is None:
            self._start_time = time.time()
        self.channels.update(
            {
                self.name + "_pos": value,
                self.name + "_time": time.time() - self._start_time,
            }
        )


def test_sweep_motor_master(beacon):
    roby = beacon.get("roby")
    roby.velocity(2000)
    roby.acceleration(10000)
    chain = AcquisitionChain()
    chain.add(
        SweepMotorMaster(roby, 0, 10, 5, 0.025),
        DebugMotorMockupPositionAcquisitionDevice("debug", roby),
    )
    s = Scan(chain, writer=None)
    with gevent.Timeout(10):
        s.run()

    data = s.get_data()
    assert len(data["debug_pos"]) == 5
