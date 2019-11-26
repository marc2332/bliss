"""Testing scan_manager module."""

import numpy
from bliss.flint.helper import scan_manager
from bliss.data.nodes.lima import ImageFormatNotSupported


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

ACQUISITION_CHAIN_3 = {
    "axis": {
        "master": {"scalars": [], "spectra": [], "images": ["lima:image"]},
        "scalars": [],
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


def test_bad_sequence__end_before_new():
    scan_info_1 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_1}

    manager = scan_manager.ScanManager(flintModel=None)
    # Disabled async consumption
    manager._set_absorb_events(False)

    manager.end_scan(scan_info_1)
    manager.new_scan(scan_info_1)
    # FIXME What to do anyway then? The manager is locked


class MockedLimaNode:
    def __init__(
        self,
        last_index=None,
        last_image_ready=None,
        video_frame_have_meaning=None,
        frame_id=None,
        image=None,
        last_image=None,
        last_live_image=None,
    ):
        self.last_index = last_index
        self.last_image_ready = last_image_ready
        self.video_frame_have_meaning = video_frame_have_meaning
        self.image = image
        self.last_image = last_image
        self.last_live_image = last_live_image
        self.frame_id = frame_id

    def get(self, index):
        # Node and view are the same, we dont care much here
        return self

    def is_video_frame_have_meaning(self):
        return self.video_frame_have_meaning

    def get_last_live_image(self):
        if isinstance(self.last_live_image, Exception):
            raise self.last_live_image
        return self.last_live_image, self.frame_id

    def get_last_image(self):
        if isinstance(self.last_image, Exception):
            raise self.last_image
        return self.last_image, self.frame_id

    def get_image(self, index):
        if isinstance(self.image, Exception):
            raise self.image
        return self.image, self.frame_id


def test_image__default():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = scan_manager.ScanManager(flintModel=None)
    # Disabled async consumption
    manager._set_absorb_events(False)

    manager.new_scan(scan_info_3)
    scan = manager.get_scan()

    image = numpy.arange(1).reshape(1, 1)
    data = {}
    data["scan_info"] = scan_info_3
    data["channel_name"] = "lima:image"
    data["channel_data_node"] = MockedLimaNode(
        frame_id=2, image=Exception(), last_image=Exception(), last_live_image=image
    )
    manager.new_scan_data("2d", "axis", data)

    manager.end_scan(scan_info_3)

    result = scan.getChannelByName("lima:image").data()
    assert result.frameId() == 2
    assert result.array().shape == (1, 1)


def test_image__disable_video():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = scan_manager.ScanManager(flintModel=None)
    # Disabled async consumption
    manager._set_absorb_events(False)

    manager.new_scan(scan_info_3)
    scan = manager.get_scan()

    image = numpy.arange(1).reshape(1, 1)
    data = {}
    data["scan_info"] = scan_info_3
    data["channel_name"] = "lima:image"
    data["channel_data_node"] = MockedLimaNode(
        frame_id=2,
        video_frame_have_meaning=False,
        image=Exception(),
        last_image=image,
        last_live_image=Exception(),
    )
    manager.new_scan_data("2d", "axis", data)

    manager.end_scan(scan_info_3)

    image = scan.getChannelByName("lima:image").data()
    assert image.frameId() == 2
    assert image.array().shape == (1, 1)


def test_image__decoding_error():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = scan_manager.ScanManager(flintModel=None)
    # Disabled async consumption
    manager._set_absorb_events(False)

    manager.new_scan(scan_info_3)
    scan = manager.get_scan()

    image = numpy.arange(1).reshape(1, 1)
    data = {}
    data["scan_info"] = scan_info_3
    data["channel_name"] = "lima:image"
    data["channel_data_node"] = MockedLimaNode(
        frame_id=2,
        video_frame_have_meaning=True,
        image=Exception(),
        last_image=image,
        last_live_image=ImageFormatNotSupported(),
    )
    manager.new_scan_data("2d", "axis", data)

    manager.end_scan(scan_info_3)

    image = scan.getChannelByName("lima:image").data()
    assert image.frameId() == 2
    assert image.array().shape == (1, 1)
