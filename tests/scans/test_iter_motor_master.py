# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time

import pytest
import gevent

from bliss.common import event
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.chain import AcquisitionDevice, AcquisitionChannel
from bliss.scanning.acquisition.motor import SweepMotorMaster, MotorMaster


class DebugMotorMockupPositionAcquisitionDevice(AcquisitionDevice):
    def __init__(self, name, motor_mockup):
        super(DebugMotorMockupPositionAcquisitionDevice, self).__init__(
            motor_mockup, name, prepare_once=True, start_once=True
        )
        self.motor_mockup = motor_mockup
        self.channels.append(AcquisitionChannel(self, name + "_start_pos", float, ()))
        self.channels.append(AcquisitionChannel(self, name + "_end_pos", float, ()))
        self.channels.append(AcquisitionChannel(self, name + "_time", float, ()))
        self._start_time = None

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def trigger(self):
        controller = self.motor_mockup.controller
        start = self.parent.start_pos
        end = self.parent.end_pos
        if self._start_time is None:
            self._start_time = time.time()
        self.channels.update(
            {
                self.name + "_start_pos": start,
                self.name + "_end_pos": end,
                self.name + "_time": time.time() - self._start_time,
            }
        )


def test_iter_sweep_motor_master(beacon):
    roby = beacon.get("roby")
    roby.velocity = 2000
    roby.acceleration = 10000
    chain = AcquisitionChain()
    start_pos = [0, 10, 20, 30, 40]
    master = SweepMotorMaster(roby, start_pos, 50, 0.1, 10)
    device = DebugMotorMockupPositionAcquisitionDevice("debug", roby)
    chain.add(master, device)
    s = Scan(chain, save=False)
    with gevent.Timeout(50):
        s.run()

    data = s.get_data()
    assert len(data["debug_start_pos"]) == 5
    assert len(data["debug_start_pos"]) == len(data["debug_end_pos"])
    for i in range(5):
        assert data["debug_start_pos"][i] == start_pos[i]
    assert list(master.sweep_pos) == list([40, 41, 42, 43, 44, 45, 46, 47, 48, 49])


def test_iter_cont_motor_master(beacon):
    roby = beacon.get("roby")
    roby.velocity = 2000
    roby.acceleration = 10000
    chain = AcquisitionChain()
    start_pos = [0, 5, 10, 15, 20, 25, 30]
    master = MotorMaster(roby, start_pos, 35, 0.05)
    device = DebugMotorMockupPositionAcquisitionDevice("debug", roby)
    chain.add(master, device)
    s = Scan(chain, save=False)
    with gevent.Timeout(10):
        s.run()

    data = s.get_data()
    assert len(data["debug_start_pos"]) == 7
    assert len(data["debug_start_pos"]) == len(data["debug_end_pos"])
    for i in range(7):
        assert data["debug_start_pos"][i] == start_pos[i]
