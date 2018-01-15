"""Test module for MCA scan."""

import numpy as np

from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.mca import McaAcquisitionDevice
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.acquisition.motor import MotorMaster


def assert_data_consistency(scan_data, realtime):
    for i in range(4):
        suffix = '_det{}'.format(i)
        assert np.array_equal(
            np.array(list(map(sum, scan_data['spectrum' + suffix]))),
            scan_data['events' + suffix])
        assert all(x == realtime for x in scan_data['realtime' + suffix])


def test_mca_continuous_soft_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(simu, npoints=3, preset_time=0.1)
    # Add counters
    mca_device.add_counters(simu.counters.spectrum.values())
    mca_device.add_counters(simu.counters.realtime.values())
    mca_device.add_counters(simu.counters.events.values())
    # Create chain
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 3, time=1.0), mca_device)
    # Run scan
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    # Checks
    assert_data_consistency(scans.get_data(scan), realtime=0.1)


def test_mca_continuous_gate_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(
        simu, block_size=2, npoints=5, trigger_mode=McaAcquisitionDevice.GATE)
    # Add counters
    mca_device.add_counters(simu.counters.spectrum.values())
    mca_device.add_counters(simu.counters.realtime.values())
    mca_device.add_counters(simu.counters.events.values())
    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0), mca_device)
    # Run scan
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    # Checks
    assert_data_consistency(scans.get_data(scan), realtime=0.5)


def test_mca_continuous_sync_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(
        simu, block_size=2, npoints=5, trigger_mode=McaAcquisitionDevice.SYNC)
    # Add counters
    mca_device.add_counters(simu.counters.spectrum.values())
    mca_device.add_counters(simu.counters.realtime.values())
    mca_device.add_counters(simu.counters.events.values())
    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0), mca_device)
    # Run scan
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    # Checks
    assert_data_consistency(scans.get_data(scan), realtime=0.4)


def test_mca_step_soft_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(simu, npoints=3, preset_time=0.1)
    # Add counters
    mca_device.add_counters(simu.counters.spectrum.values())
    mca_device.add_counters(simu.counters.realtime.values())
    mca_device.add_counters(simu.counters.events.values())
    # Create chain
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(3, m0, 0, 1), mca_device)
    # Run scan
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    # Checks
    assert_data_consistency(scans.get_data(scan), realtime=0.1)


def test_mca_default_chain_ascan(beacon):
    # Get controllers
    m0 = beacon.get('m0')
    mca = beacon.get('simu1')
    # Counters
    counters = mca.counters.spectrum.values()
    counters += mca.counters.realtime.values()
    counters += mca.counters.events.values()
    # Run scan
    scan = scans.ascan(
        m0, 0, 10, 3, 0.1, *counters, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scans.get_data(scan), realtime=0.1)
