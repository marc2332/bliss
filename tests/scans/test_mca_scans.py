"""Test module for MCA scan."""

import numpy as np

from bliss.common import scans
from bliss import setup_globals
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.common.measurementgroup import MeasurementGroup

from bliss.scanning.acquisition.motor import MotorMaster
from bliss.scanning.acquisition.mca import McaAcquisitionDevice
from bliss.scanning.acquisition.motor import LinearStepTriggerMaster
from bliss.scanning.acquisition.motor import SoftwarePositionTriggerMaster


def assert_data_consistency(scan_data, realtime):
    for i in range(4):
        suffix = "_det{}".format(i)
        assert np.array_equal(
            np.array(list(map(sum, scan_data["spectrum" + suffix]))),
            scan_data["events" + suffix],
        )
        assert all(x == realtime for x in scan_data["realtime" + suffix])


def test_mca_continuous_soft_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(simu, npoints=3, preset_time=0.1)
    # Add counters
    mca_device.add_counters(simu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 3, time=1.0), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", writer=None)
    scan.run()
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_continuous_gate_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(
        simu, block_size=2, npoints=5, trigger_mode=McaAcquisitionDevice.GATE
    )
    # Add counters
    mca_device.add_counters(simu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", writer=None)
    scan.run()
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.5)


def test_mca_continuous_sync_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(
        simu, block_size=2, npoints=5, trigger_mode=McaAcquisitionDevice.SYNC
    )
    # Add counters
    mca_device.add_counters(simu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(MotorMaster(m0, 0, 1, time=1.0), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", writer=None)
    scan.run()
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.4)


def test_mca_step_soft_scan(beacon):
    m0 = beacon.get("roby")
    # Get mca
    simu = beacon.get("simu1")
    mca_device = McaAcquisitionDevice(simu, npoints=3, preset_time=0.1)
    # Add counters
    mca_device.add_counters(simu.counters)
    # Create chain
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(3, m0, 0, 1), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", writer=None)
    scan.run()
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counters(beacon):
    # Get controllers
    m0 = beacon.get("m0")
    mca = beacon.get("simu1")
    # Counters
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, *mca.counters, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counter_namespace(beacon):
    # Get controllers
    m0 = beacon.get("m0")
    mca = beacon.get("simu1")
    # Counters
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mca.counters, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counter_namespace_from_controller(beacon):
    # Get controllers
    m0 = beacon.get("m0")
    mca = beacon.get("simu1")
    # Counters
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mca, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counter_groups(beacon):
    # Get controllers
    m0 = beacon.get("m0")
    mca = beacon.get("simu1")
    # Run scan
    scan = scans.ascan(
        m0,
        0,
        10,
        3,
        0.1,
        mca.counter_groups.realtime,
        mca.counter_groups.events,
        mca.counter_groups.spectrum,
        mca.counter_groups.det0,  # Overlap should be no problem
        return_scan=True,
        save=False,
    )
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_measurement_group(beacon):
    # Get controllers
    m0 = beacon.get("m0")
    # Add simu1 to globals
    setup_globals.simu1 = beacon.get("simu1")

    # Measurement group
    mg1 = MeasurementGroup("mygroup1", {"counters": ["simu1"]})
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mg1, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)

    # Measurement group
    mg2 = MeasurementGroup(
        "mygroup2",
        {
            "counters": [
                "simu1.counter_groups.realtime",
                "simu1.counter_groups.events",
                "simu1.counter_groups.spectrum",
                "simu1.counter_groups.det0",
            ]
        },
    )
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mg2, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_scans_with_rois(beacon):
    simu = beacon.get("simu1")
    simu.rois.clear()
    # ROI between indexes 400 and 700
    simu.rois.add_roi("my_roi", 500, 100, 200)
    scan = scans.ct(
        0.1,
        simu.counters.my_roi_det0,
        simu.counters.spectrum_det0,
        return_scan=True,
        save=False,
    )
    data = scan.get_data()
    assert data["my_roi_det0"][0] == sum(data["spectrum_det0"][0][400:700])


def test_mca_scans_with_roi_sums(beacon):
    simu = beacon.get("simu1")
    simu.rois.clear()
    # ROI between indexes 400 and 700
    simu.rois.add_roi("my_roi", 500, 100, 200)
    scan = scans.ct(
        0.1,
        simu.counters.my_roi,
        simu.counter_groups.spectrum,
        return_scan=True,
        save=False,
    )
    data = scan.get_data()
    roi_sum = sum(
        sum(data[name][0][400:700])
        for name in data.dtype.fields
        if name.startswith("spectrum")
    )
    assert data["my_roi"][0] == roi_sum
