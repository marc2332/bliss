"""Test module for PEPU scan."""

from collections import OrderedDict

import mock
import pytest
import numpy as np
import gevent.queue

from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain

from bliss.controllers.pepu import PEPU as PepuClass
from bliss.controllers.pepu import ChannelIN, ChannelOUT, ChannelCALC

from bliss.scanning.acquisition.pepu import PepuAcquisitionDevice
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster


@pytest.fixture
def pepu():

    trigger = gevent.queue.Queue()

    def idata():
        for point in pepu.mock_points:
            data = np.array(point)
            data.dtype = [(counter.name, float) for counter in pepu.counters]
            trigger.get()
            yield data

    with mock.patch('bliss.controllers.pepu.PEPU', autospec=True) as PEPU:
        pepu = PEPU.return_value
        pepu.name = 'pepu1'
        pepu.in_channels = OrderedDict([
            (i, ChannelIN(pepu, i)) for i in PepuClass.IN_CHANNELS])
        pepu.out_channels = OrderedDict([
            (i, ChannelOUT(pepu, i)) for i in PepuClass.OUT_CHANNELS])
        pepu.calc_channels = OrderedDict([
            (i, ChannelCALC(pepu, i)) for i in PepuClass.CALC_CHANNELS])
        pepu.counters = PepuClass.counters.__get__(pepu)
        stream = pepu.create_stream.return_value
        stream.idata.side_effect = idata
        pepu.software_trigger.side_effect = lambda: trigger.put(None)
        pepu.mock_points = []
        yield pepu
        # stream.start.assert_called_once_with()
        # stream.stop.assert_called_once_with()


def test_pepu_soft_scan(beacon, pepu):
    m0 = beacon.get("roby")
    # Get mca
    device = PepuAcquisitionDevice(pepu, 10)
    # Add counters
    device.add_counters(pepu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(10, m0, 0, 1), device)
    # Add data
    pepu.mock_points = [[y+x/10. for y in range(1, 15)] for x in range(10)]
    # Run scan
    scan = Scan(chain, 'pepu_test', None)
    scan.run()
    gevent.sleep(0.)
    # Checks
    data = scans.get_data(scan)
    for i, counter in enumerate(pepu.counters, 1):
        expecting = [i+x/10. for x in range(10)]
        assert list(data[counter.name]) == expecting


def test_pepu_continuous_soft_scan(beacon, pepu):
    m0 = beacon.get("roby")
    # Get mca
    device = PepuAcquisitionDevice(pepu, 10)
    # Add counters
    device.add_counters(pepu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 10, time=1.0), device)
    # Add data
    pepu.mock_points = [[y+x/10. for y in range(1, 15)] for x in range(10)]
    # Run scan
    scan = Scan(chain, 'pepu_test', None)
    scan.run()
    gevent.sleep(0.)
    # Checks
    data = scans.get_data(scan)
    for i, counter in enumerate(pepu.counters, 1):
        expecting = [i+x/10. for x in range(10)]
        assert list(data[counter.name]) == expecting


def test_pepu_default_chain_ascan(beacon, pepu):
    pytest.xfail()
    # Get controllers
    m0 = beacon.get('m0')
    # Add data
    pepu.mock_points = [[y+x/10. for y in range(1, 15)] for x in range(10)]
    # Run scan
    scan = scans.ascan(
        m0, 0, 10, 3, 0.1, *pepu.counters, return_scan=True, save=False)
    # Checks
    data = scans.get_data(scan)
    for i, counter in enumerate(pepu.counters, 1):
        expecting = [i+x/10. for x in range(10)]
        assert list(data[counter.name]) == expecting
