"""Test module for PEPU scan."""

from collections import OrderedDict

from unittest import mock
import pytest
import numpy as np
import gevent.queue

from bliss import global_map
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.common.measurementgroup import MeasurementGroup

from bliss.controllers.pepu import PEPU as PepuClass
from bliss.controllers.pepu import ChannelIN, ChannelOUT, ChannelCALC, Signal

from bliss.scanning.acquisition.pepu import PepuAcquisitionDevice
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.acquisition.motor import MotorMaster


@pytest.fixture
def pepu():

    trigger = gevent.queue.Queue()

    def idata(n):
        nb_points = pepu.create_stream.call_args[1]["nb_points"]
        assert n == nb_points
        points = [[y + x / 10. for y in range(1, 15)] for x in range(n)]
        for point in points:
            data = np.array(point)
            data.dtype = [(counter.name, float) for counter in pepu.counters]
            mode = pepu.create_stream.call_args[1]["trigger"]
            if mode.clock == Signal.SOFT:
                trigger.get()
            yield data

    def assert_data(data, n):
        for i, counter in enumerate(pepu.counters, 1):
            expecting = [i + x / 10. for x in range(n)]
            assert list(data[counter.name]) == expecting

    with mock.patch("bliss.controllers.pepu.PEPU", autospec=True) as PEPU:
        pepu = PEPU.return_value
        pepu.name = "pepu1"
        pepu.in_channels = OrderedDict(
            [(i, ChannelIN(pepu, i)) for i in PepuClass.IN_CHANNELS]
        )
        pepu.out_channels = OrderedDict(
            [(i, ChannelOUT(pepu, i)) for i in PepuClass.OUT_CHANNELS]
        )
        pepu.calc_channels = OrderedDict(
            [(i, ChannelCALC(pepu, i)) for i in PepuClass.CALC_CHANNELS]
        )
        pepu.counters = PepuClass.counters.__get__(pepu)
        stream = pepu.create_stream.return_value
        stream.idata.side_effect = idata
        pepu.software_trigger.side_effect = lambda: trigger.put(None)
        pepu.assert_data = assert_data
        yield pepu
        stream.start.assert_called_once_with()
        stream.stop.assert_called_once_with()


def test_pepu_soft_scan(session, pepu):
    m0 = session.config.get("roby")
    # Get pepu
    device = PepuAcquisitionDevice(pepu, 10)
    # Add counters
    device.add_counters(pepu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(10, m0, 0, 1), device)
    # Run scan
    scan = Scan(chain, "pepu_test", save=False)
    scan.run()
    gevent.sleep(0.)
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)


def test_pepu_continuous_soft_scan(session, pepu):
    m0 = session.config.get("roby")
    # Get pepu
    device = PepuAcquisitionDevice(pepu, 10)
    # Add counters
    device.add_counters(pepu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 10, time=1.0), device)
    # Run scan
    scan = Scan(chain, "pepu_test", save=False)
    scan.run()
    gevent.sleep(0.)
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)


def test_pepu_default_chain_with_counters(session, pepu):
    # Get controllers
    m0 = session.config.get("m0")
    # Run scan
    scan = scans.ascan(m0, 0, 10, 9, 0.01, *pepu.counters, return_scan=True, save=False)
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)


def test_pepu_default_chain_with_counter_namespace(session, pepu):
    # Get controllers
    m0 = session.config.get("m0")
    # Run scan
    scan = scans.ascan(m0, 0, 10, 9, 0.01, pepu.counters, return_scan=True, save=False)
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)


def test_pepu_default_chain_with_measurement_group(session, pepu):
    # Get controllers
    m0 = session.config.get("m0")
    # Add pepu1 to globals
    global_map.register(pepu, ["counters"])
    # Measurement group
    mg = MeasurementGroup("mygroup", {"counters": ["pepu1"]})
    # Run scan
    scan = scans.ascan(m0, 0, 10, 9, 0.01, mg, return_scan=True, save=False)
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)


def test_pepu_continuous_scan(session, pepu):
    m0 = session.config.get("roby")
    # Get pepu
    device = PepuAcquisitionDevice(pepu, 10, trigger=Signal.DI1)
    # Add counters
    device.add_counters(pepu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0), device)
    # Run scan
    scan = Scan(chain, "test", save=False)
    scan.run()
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)
