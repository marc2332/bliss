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
from bliss.scanning.acquisition.motor import TwoMotorMaster


class DebugTwoMotorMockupAcquisitionSlave(AcquisitionSlave):
    def __init__(self, name, mot1, mot2, delay):
        super(DebugTwoMotorMockupAcquisitionSlave, self).__init__(
            mot1, mot2, name=name, prepare_once=True, start_once=True
        )
        self.motors = (mot1, mot2)
        self.delay = delay

        for mot in self.motors:
            self.channels.append(AcquisitionChannel(mot.name + "_pos", float, ()))
            self.channels.append(AcquisitionChannel(mot.name + "_velocity", float, ()))

    def prepare(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def trigger(self):
        # pickup start position
        for mot in self.motors:
            self.channels.update({mot.name + "_pos": mot.position})
        # pickup velocity once started
        gevent.sleep(self.delay)
        for mot in self.motors:
            self.channels.update({mot.name + "_velocity": mot.velocity})


def test_twomotormaster_test(session):
    m1 = session.config.get("m1")
    m2 = session.config.get("m2")
    m1.velocity = 10
    m2.velocity = 10
    m1.acceleration = 10
    m2.acceleration = 10
    original_velocity_m1 = m1.velocity
    original_velocity_m2 = m2.velocity

    master = TwoMotorMaster(m1, 0, 10, m2, 0, 1, 1.)
    device = DebugTwoMotorMockupAcquisitionSlave("debug", m1, m2, .5)
    chain = AcquisitionChain()
    chain.add(master, device)
    s = Scan(chain, save=False)
    with gevent.Timeout(10):
        s.run()

    data = s.get_data()
    # check start pos
    assert data["m1_pos"] == -5.
    assert data["m2_pos"] == -.95
    # check velocity during scan
    assert data["m1_velocity"] == 10.
    assert data["m2_velocity"] == 1.
    # check velocity revert to original at the end
    assert original_velocity_m1 == m1.velocity
    assert original_velocity_m2 == m2.velocity
    # assert len(data["debug_pos"]) == 1
    # assert len(master.sweep_pos) == 5
