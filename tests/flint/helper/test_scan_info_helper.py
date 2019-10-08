"""Testing scan info helper module."""

import pytest

from bliss.flint.helper import scan_info_helper


def test_iter_channels():
    scan_info = {
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
    result = scan_info_helper.iter_channels(scan_info)
    expected = [
        scan_info_helper.Channel("diode:diode", "scalar", "diode", "timer"),
        scan_info_helper.Channel("timer:elapsed_time", "scalar", "timer", "timer"),
        scan_info_helper.Channel("timer:epoch", "scalar", "timer", "timer"),
        scan_info_helper.Channel("opium:mca1", "spectrum", "opium", "timer2"),
        scan_info_helper.Channel("lima:image1", "image", "lima", "timer2"),
    ]
    assert set(result) == set(expected)
