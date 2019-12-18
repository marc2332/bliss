"""Test module for PEPU scan."""

from collections import OrderedDict

from unittest import mock
import pytest
import numpy as np
import gevent.queue
import functools

from bliss import global_map
from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.common.measurementgroup import MeasurementGroup

from bliss.controllers.pepu import PEPU
from bliss.controllers.pepu import ChannelIN, ChannelOUT, ChannelCALC, Signal

from bliss.scanning.acquisition.pepu import PepuAcquisitionSlave
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.acquisition.motor import MotorMaster


@pytest.fixture
def pepu():

    trigger = gevent.queue.Queue()

    def idata(n, create_stream_call_kwargs=None, pepu_counters=None):
        nb_points = create_stream_call_kwargs["nb_points"]
        assert n == nb_points
        points = [
            [y + x / 10. for y in range(1, len(pepu_counters) + 1)] for x in range(n)
        ]
        for point in points:
            data = np.array(point)
            data.dtype = [(counter.name, float) for counter in pepu_counters]
            mode = create_stream_call_kwargs["trigger"]
            if mode.clock == Signal.SOFT:
                trigger.get()
            yield data

    class MockPepu(PEPU):
        def raw_write_read(self, cmd):
            return ""

        def create_stream(self, *args, **kwargs):
            stream = mock.MagicMock()
            stream.idata.side_effect = functools.partial(
                idata, create_stream_call_kwargs=kwargs, pepu_counters=self.counters
            )
            return stream

        def assert_data(self, data, n):
            for i, counter in enumerate(self.counters, 1):
                expecting = [i + x / 10. for x in range(n)]
                assert list(data[counter.name]) == expecting

        def software_trigger(self):
            trigger.put(None)

    pepu = MockPepu("pepu1", {"tcp": {"url": "nonexistent"}})

    yield pepu


def test_pepu_soft_scan(session, pepu):
    m0 = session.config.get("roby")
    # Get pepu
    device = PepuAcquisitionSlave(*pepu.counters, npoints=10)
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
    device = PepuAcquisitionSlave(*pepu.counters, npoints=10)
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
    device = PepuAcquisitionSlave(*pepu.counters, npoints=10, trigger=Signal.DI1)
    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0), device)
    # Run scan
    scan = Scan(chain, "test", save=False)
    scan.run()
    # Checks
    data = scan.get_data()
    pepu.assert_data(data, 10)
