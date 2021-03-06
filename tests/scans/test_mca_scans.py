"""Test module for MCA scan."""

import numpy as np
import itertools
import pytest

from bliss.common import scans
from bliss.scanning.scan import Scan
from bliss.scanning.chain import AcquisitionChain
from bliss.common.measurementgroup import MeasurementGroup

from bliss.scanning.acquisition.motor import MotorMaster
from bliss.scanning.acquisition.mca import McaAcquisitionSlave
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


# the scan, as it is, goes too fast for the mca acquisition to follow
# and the 'Aborted due to bad triggering' exception is raised ;
# however, the reading task of the Mca acq device cannot stop because
# it is stuck in waiting for TRIGGERED state
def test_mca_continuous_soft_scan(session):
    m0 = session.config.get("roby")
    # Get mca
    simu = session.config.get("simu1")
    mca_device = McaAcquisitionSlave(*simu.counters, npoints=3, preset_time=0.1)

    # Create chain
    chain = AcquisitionChain()
    chain.add(SoftwarePositionTriggerMaster(m0, 0, 1, 3, time=2.0), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", save=False)
    scan.run()
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_step_soft_scan(session):
    m0 = session.config.get("roby")
    # Get mca
    simu = session.config.get("simu1")
    mca_device = McaAcquisitionSlave(*simu.counters, npoints=3, preset_time=0.1)
    # Create chain
    chain = AcquisitionChain()
    chain.add(LinearStepTriggerMaster(3, m0, 0, 1), mca_device)
    # Run scan
    scan = Scan(chain, "mca_test", save=False)
    scan.run()
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counters(session):
    # Get controllers
    m0 = session.config.get("m0")
    mca = session.config.get("simu1")
    # Counters
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, *mca.counters, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counter_namespace(session):
    # Get controllers
    m0 = session.config.get("m0")
    mca = session.config.get("simu1")
    # Counters
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mca.counters, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counter_namespace_from_controller(session):
    # Get controllers
    m0 = session.config.get("m0")
    mca = session.config.get("simu1")
    # Counters
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mca, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_default_chain_with_counter_groups(session):
    # Get controllers
    m0 = session.config.get("m0")
    mca = session.config.get("simu1")
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


def test_mca_default_chain_with_measurement_group(session):
    # Get controllers
    m0 = session.config.get("m0")
    # Add simu1 to globals
    simu1 = session.config.get("simu1")

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
                cnt.fullname
                for cnt in itertools.chain(
                    simu1.counter_groups.realtime,
                    simu1.counter_groups.events,
                    simu1.counter_groups.spectrum,
                    simu1.counter_groups.det0,
                )
            ]
        },
    )
    # Run scan
    scan = scans.ascan(m0, 0, 10, 3, 0.1, mg2, return_scan=True, save=False)
    # Checks
    assert_data_consistency(scan.get_data(), realtime=0.1)


def test_mca_scans_with_rois(session):
    simu = session.config.get("simu1")
    simu.rois.clear()
    simu.rois.set("my_roi", 400, 700)
    scan = scans.ct(
        0.1, simu.counters.my_roi_det0, simu.counters.spectrum_det0, return_scan=True
    )
    data = scan.get_data()
    assert data["my_roi_det0"][0] == sum(data["spectrum_det0"][0][400:700])


def test_mca_scans_with_roi_sums(session):
    simu = session.config.get("simu1")
    simu.rois.clear()
    simu.rois.set("my_roi", 400, 700)
    scan = scans.ct(
        0.1, simu.counters.my_roi, simu.counter_groups.spectrum, return_scan=True
    )
    data = scan.get_data()
    roi_sum = sum(
        sum(data[name][0][400:700])
        for name in data.keys()
        if name.find("spectrum") > -1
    )
    assert data["my_roi"][0] == roi_sum
