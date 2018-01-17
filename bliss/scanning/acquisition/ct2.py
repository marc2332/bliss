# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""CT2 (P201/C208) bliss acquisition master"""

import gevent.event

from bliss.common.event import dispatcher
from bliss.scanning.chain import AcquisitionMaster
from bliss.controllers.ct2.device import (AcqMode, AcqStatus,
                                          StatusSignal, PointNbSignal,
                                          ErrorSignal)


class CT2AcquisitionMaster(AcquisitionMaster):

    SoftTrigModes = AcqMode.IntTrigMulti, AcqMode.SoftTrigReadout


    def __init__(self, device, npoints=1, acq_expo_time=1.,
                 acq_point_period=None,
                 acq_mode=AcqMode.IntTrigMulti):
        name = type(device).__name__
        self.acq_expo_time = acq_expo_time
        self.acq_mode = acq_mode
        self.first_trigger = None
        self.status = None
        self.last_point_ready = None
        self.last_error = None
        self.point_event = gevent.event.Event()
        self.point_event.set()
        if acq_mode in self.SoftTrigModes:
            trigger_type = self.SOFTWARE
        else:
            trigger_type = self.HARDWARE
        kwargs = dict(npoints=npoints, prepare_once=True, start_once=True,
                      trigger_type=trigger_type)
        super(CT2AcquisitionMaster, self).__init__(device, name, **kwargs)
        dispatcher.connect(self.__on_event, sender=device)

    def __on_event(self, value, signal):
        if signal == StatusSignal:
            self.status = value
        elif signal == PointNbSignal:
            self.last_point_ready = value
            if value >= 0:
                self.point_event.set()
        elif signal == ErrorSignal:
            self.last_error = value

    def prepare(self):
        self.first_trigger = True
        device = self.device
        device.acq_mode = self.acq_mode
        device.acq_expo_time = self.acq_expo_time
        device.acq_nb_points = self.npoints
        self.device.prepare_acq()

    def start(self):
        pass

    def stop(self):
        self.device.stop_acq()

    def trigger(self):
        if self.first_trigger:
            self.first_trigger = False
            self.device.start_acq()
        else:
            self.device.trigger_point()

    def wait_ready(self):
        self.point_event.wait()
        self.point_event.clear()
