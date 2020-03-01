# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

import pytest
import gevent

from bliss.common import event
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain, AcquisitionSlave
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.acquisition.motor import SweepMotorMaster


class DebugMotorMockupPositionAcquisitionSlave(AcquisitionSlave):
    def __init__(self, name, motor_mockup):
        super(DebugMotorMockupPositionAcquisitionSlave, self).__init__(
            motor_mockup, name=name, prepare_once=True, start_once=True
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
        value = self.motor_mockup.position
        if self._start_time is None:
            self._start_time = time.time()
        self.channels.update(
            {
                self.name + "_pos": value,
                self.name + "_time": time.time() - self._start_time,
            }
        )


def test_sweep_motor_master(session):
    roby = session.config.get("roby")
    roby.velocity = 2000
    roby.acceleration = 10000
    master = SweepMotorMaster(roby, 0, 10, 0.025, 5)
    device = DebugMotorMockupPositionAcquisitionSlave("debug", roby)
    chain = AcquisitionChain()
    chain.add(master, device)
    s = Scan(chain, save=False)
    with gevent.Timeout(10):
        s.run()

    data = s.get_data()
    assert len(data["debug_pos"]) == 1
    assert len(master.sweep_pos) == 5
