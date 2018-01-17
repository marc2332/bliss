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
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(simu, npoints=3, preset_time=0.1)
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 3, time=1.2), mca_device)
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    scan_data = scans.get_data(scan)
    for i in range(4):
        prefix = 'det{}_'.format(i)
        assert np.array_equal(
            np.array(list(map(sum, scan_data[prefix+'spectrum']))),
            scan_data[prefix+'events'])
        assert all(x == 0.1 for x in scan_data[prefix + 'realtime'])


def test_mca_step_soft_scan(beacon):
    m0 = beacon.get("roby")
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(simu, npoints=3, preset_time=0.1)
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(3, m0, 0, 1), mca_device)
    scan = Scan(chain, 'mca_test', None)
    scan.run()
    scan_data = scans.get_data(scan)
    for i in range(4):
        prefix = 'det{}_'.format(i)
        assert np.array_equal(
            np.array(list(map(sum, scan_data[prefix + 'spectrum']))),
            scan_data[prefix+'events'])
        assert all(x == 0.1 for x in scan_data[prefix + 'realtime'])
