# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import itertools
import gevent
import time
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionDevice
from bliss.controllers.simulation_diode import SimulationDiodeSamplingCounter


class CustomSimulationDiode(SimulationDiodeSamplingCounter):
    diode_nb = itertools.count()

    def __init__(self):
        SimulationDiodeSamplingCounter.__init__(
            self, "diode%d" % next(CustomSimulationDiode.diode_nb), None
        )
        self.store_time = list()
        self.store_values = list()
        self.read_exception = False

    def read(self, *args, **kwargs):
        if self.read_exception:
            raise RuntimeError("Diode reading exception")
        self.store_time.append(time.time())
        value = SimulationDiodeSamplingCounter.read(self, *args, **kwargs)
        self.store_values.append(value)
        return value


@pytest.fixture
def diode():
    return CustomSimulationDiode()


@pytest.fixture
def bad_diode():
    diode = CustomSimulationDiode()
    diode.read_exception = True
    return diode


class CustomSamplingCounterAcquisitionDevice(SamplingCounterAcquisitionDevice):
    def __init__(self, *args, **kwargs):
        SamplingCounterAcquisitionDevice.__init__(self, *args, **kwargs)

        self.trigger_fail = False
        self.trigger_delay = 0
        self.stop_flag = False
        self.start_time = None
        self.stop_time = None

    def start(self, *args, **kwargs):
        self.start_time = time.time()
        return SamplingCounterAcquisitionDevice.start(self, *args, **kwargs)

    def stop(self, *args, **kwargs):
        self.stop_time = time.time()
        self.stop_flag = True
        return SamplingCounterAcquisitionDevice.stop(self, *args, **kwargs)

    def trigger(self):
        if self.trigger_fail:
            raise RuntimeError("Trigger failure")
        else:
            if self.trigger_delay:
                gevent.sleep(self.trigger_delay)
            return SamplingCounterAcquisitionDevice.trigger(self)


@pytest.fixture
def diode_acq_device_factory():
    class SamplingCounterAcqDeviceFactory(object):
        def get(self, *args, **kwargs):
            trigger_fail = kwargs.pop("trigger_fail", False)
            trigger_delay = kwargs.pop("trigger_delay", 0)
            diode = CustomSimulationDiode()
            acq_device = CustomSamplingCounterAcquisitionDevice(diode, *args, **kwargs)
            acq_device.trigger_fail = trigger_fail
            acq_device.trigger_delay = trigger_delay
            return acq_device

    return SamplingCounterAcqDeviceFactory()
