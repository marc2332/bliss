"""Testing scan model."""

import pytest
import numpy
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
            "images": ["lima:image"],
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


def test_scan_data_update_single_image_channel():
    scan = scan_info_helper.create_scan_model(SCATTER_SCAN_INFO)
    channel = scan.getChannelByName("lima:image")
    event = scan_model.ScanDataUpdateEvent(scan, channel=channel)
    expected = {"lima:image"}
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


def test_scan_sealed():
    scan = scan_model.Scan()
    scan.setScanInfo({"foo": "bar"})
    scan.seal()
    with pytest.raises(scan_model.SealedError):
        scan.setScanInfo({"foo": "bar"})


def test_recurssive_sealed():
    scan = scan_model.Scan()
    device = scan_model.Device(scan)
    device.setName("device")
    channel = scan_model.Channel(device)
    channel.setName("channel")
    scan.seal()
    with pytest.raises(scan_model.SealedError):
        device.setName("device2")
    with pytest.raises(scan_model.SealedError):
        channel.setName("channel2")


def test_cache_result():
    scan = scan_model.Scan()
    scan.seal()

    obj = "foo"
    result = numpy.arange(10)

    # Not yet in the cache
    assert not scan.hasCachedResult(obj)
    with pytest.raises(KeyError):
        scan.getCachedResult(obj)

    # Set the cache
    scan.setCachedResult(obj, result)
    assert scan.hasCachedResult(obj)
    assert scan.getCachedResult(obj) is result

    # Overwrite the cache
    result2 = numpy.arange(8)
    scan.setCachedResult(obj, result2)
    assert scan.hasCachedResult(obj)
    assert scan.getCachedResult(obj) is result2


def test_cache_validation():
    scan = scan_model.Scan()
    scan.seal()

    obj = "foo"
    result = "Not valid"
    version = 1

    # Not yet in the cache
    assert not scan.hasCacheValidation(obj, version)
    with pytest.raises(KeyError):
        scan.getCacheValidation(obj, version)

    # Set the cache
    scan.setCacheValidation(obj, version, result)
    assert scan.hasCacheValidation(obj, version)
    assert not scan.hasCacheValidation(obj, version + 1)
    assert scan.getCacheValidation(obj, version) is result
    with pytest.raises(KeyError):
        assert scan.getCacheValidation(obj, version + 1)

    # Overwrite the cache
    result2 = None
    with pytest.raises(KeyError):
        # The version have to be updated
        scan.setCacheValidation(obj, version, result2)
    version = version + 1
    scan.setCacheValidation(obj, version, result2)
    assert scan.hasCacheValidation(obj, version)
    assert scan.getCacheValidation(obj, version) is result2


def test_device():
    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master.setName("master")
    device = scan_model.Device(scan)
    device.setName("device")
    device.setMaster(master)
    scan.seal()

    assert device.master() is master
    assert device.topMaster() is master
    assert master.isMaster()
    assert not device.isMaster()
    assert master.master() is None
    assert master.topMaster() is master
    assert device.scan() is scan


def test_channel():
    scan = scan_model.Scan()
    master = scan_model.Device(scan)
    master.setName("master")
    device = scan_model.Device(scan)
    device.setName("device")
    device.setMaster(master)
    counter = scan_model.Channel(device)
    counter.setName("channel1")
    counter.setType(scan_model.ChannelType.COUNTER)
    spectrum = scan_model.Channel(device)
    spectrum.setName("channel2")
    spectrum.setType(scan_model.ChannelType.SPECTRUM)
    image = scan_model.Channel(device)
    image.setName("channel2")
    image.setType(scan_model.ChannelType.IMAGE)
    scan.seal()

    # Test getter

    assert counter.master() is master
    assert counter.device() is device

    # Test types

    assert not counter.hasData()
    assert counter.ndim == 1
    array = numpy.array([0, 1, 2])
    counter.setData(scan_model.Data(scan, array))
    assert counter.hasData()
    assert array is counter.data().array()

    # Data can be updated
    array = numpy.array([0, 1, 2, 4])
    counter.setData(scan_model.Data(scan, array))
    assert array is counter.data().array()

    # Except with invalid data type
    array = numpy.arange(4).reshape(2, 2)
    with pytest.raises(ValueError):
        counter.setData(scan_model.Data(scan, array))

    assert spectrum.ndim == 1
    array = numpy.array([0, 1, 2])
    spectrum.setData(scan_model.Data(scan, array))
    assert spectrum.hasData()
    assert array is spectrum.data().array()

    assert image.ndim == 2
    array = numpy.arange(4).reshape(2, 2)
    image.setData(scan_model.Data(scan, array))
    assert array is image.data().array()
