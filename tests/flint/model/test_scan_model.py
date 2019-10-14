"""Testing scan model."""

import numpy
from silx.gui import qt
from bliss.flint.model import scan_model
from bliss.flint.helper import scan_info_helper


SCATTER_SCAN_INFO = {
    "acquisition_chain": {
        "master_time1": {
            "display_names": {},
            "master": {
                "display_names": {},
                "images": [],
                "scalars": ["device1:channel1", "device2:channel1", "device2:channel2"],
                "scalars_units": {"device2_channel1": "mm", "device3:channel1": "mm"},
                "spectra": [],
            },
            "scalars": ["device3:channel1", "device4:channel1", "master_time1:index"],
            "scalars_units": {"master_time1:index": "s"},
        }
    },
    "data_dim": 2,
}


def test_scan_data_update_whole_channels():
    scan = scan_info_helper.create_scan_model(SCATTER_SCAN_INFO)
    event = scan_model.ScanDataUpdateEvent(scan)
    expected = {
        "master_time1:index",
        "device1:channel1",
        "device2:channel1",
        "device2:channel2",
        "device3:channel1",
        "device4:channel1",
    }
    assert event.updatedChannelNames() == expected


def test_scan_data_update_single_channel():
    scan = scan_info_helper.create_scan_model(SCATTER_SCAN_INFO)
    channel = scan.getChannelByName("device2:channel2")
    event = scan_model.ScanDataUpdateEvent(scan, channel=channel)
    expected = {"device2:channel2"}
    assert event.updatedChannelNames() == expected


def test_scan_data_update_master_channels():
    scan = scan_info_helper.create_scan_model(SCATTER_SCAN_INFO)
    device = scan.getDeviceByName("master_time1")
    event = scan_model.ScanDataUpdateEvent(scan, masterDevice=device)
    expected = {
        "master_time1:index",
        "device1:channel1",
        "device2:channel1",
        "device2:channel2",
        "device3:channel1",
        "device4:channel1",
    }
    assert event.updatedChannelNames() == expected
