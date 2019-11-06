# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import time
import random
import itertools
import pytest
import gevent


from bliss.controllers.counter import SamplingCounterController
from bliss.controllers.simulation_diode import SimulationDiodeSamplingCounter
from bliss.scanning.channel import AcquisitionChannel
from bliss.scanning.chain import AcquisitionMaster, AcquisitionSlave
from bliss.scanning.acquisition.counter import SamplingCounterAcquisitionSlave
from bliss.scanning import scan_meta as scan_meta_module


class DummyMaster(AcquisitionMaster):
    def __init__(self, *args, **kwargs):
        AcquisitionMaster.__init__(self, *args, **kwargs)
        self.child_prepared = 0
        self.child_started = 0

    def prepare(self):
        self.wait_slaves_prepare()
        self.child_prepared = sum((slave.prepared_flag for slave in self.slaves))

    def start(self):
        self.child_started = sum((slave.started_flag for slave in self.slaves))
        if not self.parent:
            # top master
            self.trigger()

    def trigger(self):
        self.trigger_slaves()

    def stop(self):
        pass


class DummyDevice(AcquisitionSlave):
    def __init__(self, *args, **kwargs):
        self.sleep_time = kwargs.pop("sleep_time", 0)
        AcquisitionSlave.__init__(self, *args, **kwargs)
        self.channels.append(AcquisitionChannel(f"{self.name}:pi", float, ()))
        self.channels.append(AcquisitionChannel(f"{self.name}:nb", float, ()))
        self.nb_trigger = 0
        self.prepared_flag = False
        self.started_flag = False

    def prepare(self):
        gevent.sleep(self.sleep_time)
        self.prepared_flag = True

    def start(self):
        gevent.sleep(self.sleep_time)
        self.started_flag = True

    def trigger(self):
        self.channels.update_from_iterable((3.14, self.nb_trigger))
        self.nb_trigger += 1

    def stop(self):
        pass


class CustomSimulationDiodeController(SamplingCounterController):
    def read(self, counter):
        if counter.read_exception:
            raise RuntimeError("Diode reading exception")
        counter.store_time.append(time.time())

        gevent.sleep(0.01)
        value = random.randint(-100, 100)
        counter.store_values.append(value)
        return value


class CustomSimulationDiode(SimulationDiodeSamplingCounter):
    diode_nb = itertools.count()

    def __init__(self):
        SimulationDiodeSamplingCounter.__init__(
            self,
            "diode%d" % next(CustomSimulationDiode.diode_nb),
            CustomSimulationDiodeController(),
        )
        self.store_time = list()
        self.store_values = list()
        self.read_exception = False


@pytest.fixture
def diode():
    return CustomSimulationDiode()


@pytest.fixture
def bad_diode():
    diode = CustomSimulationDiode()
    diode.read_exception = True
    return diode


class CustomSamplingCounterAcquisitionSlave(SamplingCounterAcquisitionSlave):
    def __init__(self, *args, **kwargs):
        SamplingCounterAcquisitionSlave.__init__(self, *args, **kwargs)

        self.trigger_fail = False
        self.trigger_delay = 0
        self.stop_flag = False
        self.start_time = None
        self.stop_time = None

    def start(self, *args, **kwargs):
        self.start_time = time.time()
        return SamplingCounterAcquisitionSlave.start(self, *args, **kwargs)

    def stop(self, *args, **kwargs):
        self.stop_time = time.time()
        self.stop_flag = True
        return SamplingCounterAcquisitionSlave.stop(self, *args, **kwargs)

    def trigger(self):
        if self.trigger_fail:
            raise RuntimeError("Trigger failure")
        else:
            if self.trigger_delay:
                gevent.sleep(self.trigger_delay)
            return SamplingCounterAcquisitionSlave.trigger(self)


@pytest.fixture
def diode_acq_device_factory():
    class SamplingCounterAcqDeviceFactory(object):
        def get(self, *args, **kwargs):
            trigger_fail = kwargs.pop("trigger_fail", False)
            trigger_delay = kwargs.pop("trigger_delay", 0)
            diode = CustomSimulationDiode()
            acq_device = CustomSamplingCounterAcquisitionSlave(diode, *args, **kwargs)
            acq_device.trigger_fail = trigger_fail
            acq_device.trigger_delay = trigger_delay
            return acq_device, diode

    return SamplingCounterAcqDeviceFactory()


@pytest.fixture
def dummy_acq_device():
    class DummyAcqDeviceFactory(object):
        def get(self, *args, **kwargs):
            return DummyDevice(*args, **kwargs)

    return DummyAcqDeviceFactory()


@pytest.fixture
def dummy_acq_master():
    class DummyAcqMasterFactory(object):
        def get(self, *args, **kwargs):
            return DummyMaster(*args, **kwargs)

    return DummyAcqMasterFactory()


@pytest.fixture
def scan_meta():
    s = scan_meta_module.create_user_scan_meta()
    yield s
