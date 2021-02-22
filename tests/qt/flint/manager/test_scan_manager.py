"""Testing scan_manager module."""

import numpy
from bliss.flint.manager import scan_manager
from bliss.data.lima_image import ImageFormatNotSupported
from bliss.data.lima_image import Frame


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


class MockedScanManager(scan_manager.ScanManager):
    def emit_scan_started(self, scan_info):
        self.on_scan_started(scan_info["node_name"], scan_info)

    def emit_scan_finished(self, scan_info):
        self.on_scan_finished(scan_info["node_name"], scan_info)

    def emit_scalar_updated(self, scan_info, channel_name, data):
        scan_db_name = scan_info["node_name"]
        self.on_scalar_data_received(scan_db_name, channel_name, 0, data)

    def emit_lima_ref_updated(self, scan_info, channel_name, source_node):
        scan_db_name = scan_info["node_name"]
        self.on_lima_ref_received(scan_db_name, channel_name, 2, source_node, None)


def test_interleaved_scans():
    scan_info_1 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_1}
    scan_info_2 = {"node_name": "scan2", "acquisition_chain": ACQUISITION_CHAIN_2}

    manager = MockedScanManager(flintModel=None)
    # Disabled async consumption

    scans = manager.get_alive_scans()
    assert len(scans) == 0

    manager.emit_scan_started(scan_info_1)
    scans = manager.get_alive_scans()
    assert len(scans) == 1
    assert scans[0].scanInfo() == scan_info_1

    manager.emit_scan_started(scan_info_2)
    manager.emit_scalar_updated(scan_info_1, "axis:roby", numpy.arange(2))
    manager.emit_scalar_updated(scan_info_2, "axis:robz", numpy.arange(3))
    manager.wait_data_processed()
    scans = manager.get_alive_scans()
    assert len(scans) == 2

    manager.emit_scan_finished(scan_info_1)
    scans = manager.get_alive_scans()
    assert len(scans) == 1
    assert scans[0].scanInfo() == scan_info_2

    manager.emit_scan_finished(scan_info_2)
    scans = manager.get_alive_scans()
    assert len(scans) == 0


def test_sequencial_scans():
    scan_info_1 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_1}
    scan_info_2 = {"node_name": "scan2", "acquisition_chain": ACQUISITION_CHAIN_2}

    manager = MockedScanManager(flintModel=None)

    manager.emit_scan_started(scan_info_1)
    manager.emit_scalar_updated(scan_info_1, "axis:roby", numpy.arange(2))
    manager.wait_data_processed()
    scans = manager.get_alive_scans()
    assert len(scans) == 1
    manager.emit_scan_finished(scan_info_1)
    assert manager.get_alive_scans() == []
    assert scans[0].scanInfo() == scan_info_1

    manager.emit_scan_started(scan_info_2)
    manager.emit_scalar_updated(scan_info_2, "axis:robz", numpy.arange(3))
    manager.wait_data_processed()
    scans = manager.get_alive_scans()
    assert len(scans) == 1
    manager.emit_scan_finished(scan_info_2)
    assert manager.get_alive_scans() == []
    assert scans[0].scanInfo() == scan_info_2


def test_bad_sequence__end_before_new():
    scan_info_1 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_1}

    manager = MockedScanManager(flintModel=None)

    manager.emit_scan_finished(scan_info_1)
    manager.emit_scan_started(scan_info_1)
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
        return Frame(self.last_live_image, self.frame_id, "video")

    def get_last_image(self):
        if isinstance(self.last_image, Exception):
            raise self.last_image
        return Frame(self.last_image, self.frame_id, "file")

    def get_image(self, index):
        if isinstance(self.image, Exception):
            raise self.image
        return self.image


def test_image__default():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = MockedScanManager(flintModel=None)

    manager.emit_scan_started(scan_info_3)
    scan = manager.get_alive_scans()[0]

    image = numpy.arange(1).reshape(1, 1)
    source_node = MockedLimaNode(
        frame_id=2, image=Exception(), last_image=Exception(), last_live_image=image
    )
    manager.emit_lima_ref_updated(scan_info_3, "lima:image", source_node)

    manager.emit_scan_finished(scan_info_3)

    result = scan.getChannelByName("lima:image").data()
    assert result.frameId() == 2
    assert result.array().shape == (1, 1)


def test_image__disable_video():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = MockedScanManager(flintModel=None)

    manager.emit_scan_started(scan_info_3)
    scan = manager.get_alive_scans()[0]

    image = numpy.arange(1).reshape(1, 1)
    source_node = MockedLimaNode(
        frame_id=2,
        video_frame_have_meaning=False,
        image=Exception(),
        last_image=image,
        last_live_image=Exception(),
    )
    manager.emit_lima_ref_updated(scan_info_3, "lima:image", source_node)

    manager.emit_scan_finished(scan_info_3)

    image = scan.getChannelByName("lima:image").data()
    assert image.frameId() == 2
    assert image.array().shape == (1, 1)


def test_image__decoding_error():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = MockedScanManager(flintModel=None)

    manager.emit_scan_started(scan_info_3)
    scan = manager.get_alive_scans()[0]

    image = numpy.arange(1).reshape(1, 1)
    source_node = MockedLimaNode(
        frame_id=2,
        video_frame_have_meaning=True,
        image=Exception(),
        last_image=image,
        last_live_image=ImageFormatNotSupported(),
    )
    manager.emit_lima_ref_updated(scan_info_3, "lima:image", source_node)

    manager.emit_scan_finished(scan_info_3)

    image = scan.getChannelByName("lima:image").data()
    assert image.frameId() == 2
    assert image.array().shape == (1, 1)


def test_prefered_user_refresh():
    scan_info_3 = {"node_name": "scan1", "acquisition_chain": ACQUISITION_CHAIN_3}

    manager = MockedScanManager(flintModel=None)

    manager.emit_scan_started(scan_info_3)
    scan = manager.get_alive_scans()[0]
    channel = scan.getChannelByName("lima:image")
    channel.setPreferedRefreshRate("foo", 500)

    image = numpy.arange(1).reshape(1, 1)

    source_node = MockedLimaNode(
        frame_id=2,
        video_frame_have_meaning=False,
        image=Exception(),
        last_image=image,
        last_live_image=Exception(),
    )

    for i in range(10):
        source_node.frame_id = i
        manager.emit_lima_ref_updated(scan_info_3, "lima:image", source_node)

    manager.emit_scan_finished(scan_info_3)

    # The first end the last
    assert channel.updatedCount() == 2
    # The last is there
    assert channel.data().frameId() == 9
