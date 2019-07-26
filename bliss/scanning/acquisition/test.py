# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from ..chain import AcquisitionDevice, AcquisitionMaster
import gevent
import time


class TestAcquisitionDevice(AcquisitionDevice):
    def __init__(self, device, sleep_time=1, **keys):
        AcquisitionDevice.__init__(self, device, **keys)
        self.sleep_time = sleep_time

    def __str__(self):
        return "(acq.dev) " + self.device

    def prepare(self):
        print("preparing device", self.device)
        gevent.sleep(self.sleep_time)
        print("done preparing device", self.device)

    def start(self):
        print("starting device", self.device)
        gevent.sleep(self.sleep_time)
        print("done starting device", self.device)

    def stop(self):
        print("stopping device", self.device)
        gevent.sleep(self.sleep_time)
        print("done stopping device", self.device)

    def trigger(self):
        print("triggered", self.device, time.time())


class TestAcquisitionMaster(AcquisitionMaster):
    def __init__(self, device):
        AcquisitionMaster.__init__(self, device)

    def __str__(self):
        return "(master) " + self.device

    def prepare(self):
        print("preparing master", self.device)
        print("my slaves are", self.slaves)
        gevent.sleep(2)
        print("done preparing master", self.device)

    def start(self):
        print("starting master", self.device)
        gevent.sleep(2)
        print("done starting master", self.device)
