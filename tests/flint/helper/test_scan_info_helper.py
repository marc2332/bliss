"""Testing scan info helper module."""

import pytest

from bliss.flint.helper import scan_info_helper
from bliss.flint.model import scan_model


SCAN_INFO = {
    "acquisition_chain": {
        "timer": {
            "display_names": {"diode:diode": "diode", "images": []},
            "master": {
                "display_names": {
                    "timer:elapsed_time": "elapsed_time",
                    "timer:epoch": "epoch",
                },
                "images": [],
                "scalars": ["timer:elapsed_time", "timer:epoch"],
                "scalars_units": {"timer:elapsed_time": "s", "timer:epoch": "s"},
                "spectra": [],
            },
            "scalars": ["diode:diode"],
            "scalars_units": {"diode:diode": None, "spectra": []},
        },
        "timer2": {"spectra": ["opium:mca1"], "images": ["lima:image1"]},
    }
}


def test_iter_channels():
    result = scan_info_helper.iter_channels(SCAN_INFO)
    expected = [
        scan_info_helper.Channel("diode:diode", "scalar", "diode", "timer"),
        scan_info_helper.Channel("timer:elapsed_time", "scalar", "timer", "timer"),
        scan_info_helper.Channel("timer:epoch", "scalar", "timer", "timer"),
        scan_info_helper.Channel("opium:mca1", "spectrum", "opium", "timer2"),
        scan_info_helper.Channel("lima:image1", "image", "lima", "timer2"),
    ]
    assert set(result) == set(expected)


def test_create_scan_model():
    scan = scan_info_helper.create_scan_model(SCAN_INFO)
    assert scan.isSealed()

    channelCount = 0
    deviceCount = len(list(scan.devices()))
    for device in scan.devices():
        channelCount += len(list(device.channels()))
    assert channelCount == 5
    assert deviceCount == 5

    expected = [
        ("diode:diode", scan_model.ChannelType.COUNTER, "diode", "timer"),
        ("timer:elapsed_time", scan_model.ChannelType.COUNTER, "timer", "timer"),
        ("timer:epoch", scan_model.ChannelType.COUNTER, "timer", "timer"),
        ("opium:mca1", scan_model.ChannelType.SPECTRUM, "opium", "timer2"),
        ("lima:image1", scan_model.ChannelType.IMAGE, "lima", "timer2"),
    ]

    for channel_info in expected:
        name, kind, device, master = channel_info
        channel = scan.getChannelByName(name)
        assert channel.name() == name
        assert channel.type() == kind
        assert channel.device().name() == device
        if device == master:
            assert channel.device().master() is None
        else:
            assert channel.device().master().name() == master
