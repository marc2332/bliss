"""Testing scan_manager module."""

import numpy
from bliss.flint.helper import scan_manager


ACQUISITION_CHAIN_1 = {
    "axis": {
        "master": {"scalars": ["axis:roby"], "spectra": [], "images": []},
        "scalars": ["timer:elapsed_time", "axis:roby"],
        "spectra": [],
        "images": [],
    }
}

ACQUISITION_CHAIN_2 = {
    "axis": {
        "master": {"scalars": ["axis:robz"], "spectra": [], "images": []},
        "scalars": ["timer:elapsed_time", "axis:robz"],
        "spectra": [],
        "images": [],
    }
}


def test_interleaved_scans():
    scan_info_1 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_1}
    scan_info_2 = {"node_name": "scan2", "acquisition_chain": ACQUISITION_CHAIN_2}

    manager = scan_manager.ScanManager(flintModel=None)
    # Disabled async consumption
    manager._set_absorb_events(False)

    manager.new_scan(scan_info_1)
    manager.new_scan(scan_info_2)
    data1 = {"scan_info": scan_info_1, "data": {"axis:roby": numpy.arange(2)}}
    manager.new_scan_data("0d", "axis", data=data1)
    data2 = {"scan_info": scan_info_2, "data": {"axis:robz": numpy.arange(3)}}
    manager.new_scan_data("0d", "axis", data=data2)
    scan = manager.get_scan()
    assert scan is not None
    manager.end_scan(scan_info_1)
    assert manager.get_scan() is None
    manager.end_scan(scan_info_2)
    assert scan.scanInfo() == scan_info_1


def test_double_scans():
    scan_info_1 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_1}
    scan_info_2 = {"node_name": "scan2", "acquisition_chain": ACQUISITION_CHAIN_2}

    manager = scan_manager.ScanManager(flintModel=None)
    # Disabled async consumption
    manager._set_absorb_events(False)

    manager.new_scan(scan_info_1)
    data1 = {"scan_info": scan_info_1, "data": {"axis:roby": numpy.arange(2)}}
    manager.new_scan_data("0d", "axis", data=data1)
    scan = manager.get_scan()
    assert scan is not None
    manager.end_scan(scan_info_1)
    assert manager.get_scan() is None
    assert scan.scanInfo() == scan_info_1

    manager.new_scan(scan_info_2)
    data2 = {"scan_info": scan_info_2, "data": {"axis:robz": numpy.arange(3)}}
    manager.new_scan_data("0d", "axis", data=data2)
    scan = manager.get_scan()
    assert scan is not None
    manager.end_scan(scan_info_2)
    assert manager.get_scan() is None
    assert scan.scanInfo() == scan_info_2
