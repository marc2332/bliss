"""Test module for MCA scan."""

import numpy as np

from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.scanning.acquisition.mca import McaAcquisitionDevice
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster


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
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 3, time=1.2), mca_device)
    # Run scan
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    scan_data = scans.get_data(scan)
    # Checks
    for i in range(4):
        suffix = '_det{}'.format(i)
        assert np.array_equal(
            np.array(list(map(sum, scan_data['spectrum' + suffix]))),
            scan_data['events' + suffix])
        assert all(x == 0.1 for x in scan_data['realtime' + suffix])


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
    scan_data = scans.get_data(scan)
    # Checks
    for i in range(4):
        suffix = '_det{}'.format(i)
        assert np.array_equal(
            np.array(list(map(sum, scan_data['spectrum' + suffix]))),
            scan_data['events' + suffix])
        assert all(x == 0.1 for x in scan_data['realtime' + suffix])
