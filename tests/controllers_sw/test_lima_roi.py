import numpy
import pytest
import fabio

from typing import NamedTuple, Tuple, Optional
from bliss.common.scans import ct, loopscan


class LimParams(NamedTuple):
    rotation: str
    flip: Tuple[bool, bool]
    binning: Tuple[int, int]
    roi: Tuple[int, int, int, int]


LimParamList = [
    LimParams("90", (True, False), (1, 1), (1, 2, 3, 4)),
    LimParams("180", (True, True), (1, 1), (1, 2, 3, 4)),
    LimParams("90", (False, True), (1, 1), (1, 2, 3, 4)),
    LimParams("270", (False, True), (1, 1), (1, 2, 3, 4)),
    LimParams("NONE", (False, False), (1, 1), (1, 2, 3, 4)),
    LimParams("90", (True, False), (1, 1), (600, 700, 400, 300)),
    LimParams("90", (True, False), (1, 1), (0, 0, 10, 20)),
    LimParams("180", (False, True), (1, 1), (0, 0, 10, 20)),
    LimParams("270", (True, True), (1, 1), (0, 0, 10, 20)),
    LimParams("270", (False, True), (1, 1), (0, 0, 1024, 1024)),
    LimParams("90", (True, False), (2, 2), (10, 20, 30, 40)),
    LimParams("90", (True, False), (30, 30), (2, 3, 5, 6)),
]


@pytest.mark.parametrize("lima_params", LimParamList)
def test_lima_roi(beacon, lima_simulator, lima_params):
    ls = beacon.get("lima_simulator")
    ls.proxy.image_flip = lima_params.flip
    ls.proxy.image_rotation = lima_params.rotation
    ls.proxy.image_bin = lima_params.binning
    ls.proxy.image_roi = lima_params.roi
    ls.image.sync()

    _roi = ls.image.roi.to_array()
    _rot = ls.image.rotation
    _flip = ls.image.flip
    _bin = ls.image.binning

    ffrefroi = ls._image_params._calc_roi(_roi, _rot, _flip, _bin, inverse=True)

    ls.proxy.image_bin = [1, 1]
    ls.proxy.image_flip = [False, False]
    ls.proxy.image_rotation = "None"

    assert all(ffrefroi == ls.proxy.image_roi)

    reverse = ls._image_params._calc_roi(
        ffrefroi, ls.image.rotation, ls.image.flip, ls.image.binning
    )
    assert all(reverse == numpy.array(lima_params.roi))


@pytest.fixture
def lima_tmpdir(tmpdir):
    yield tmpdir
    tmpdir.remove()


LimParamList2 = [
    LimParams("90", (True, False), (1, 1), (1, 2, 3, 4)),
    LimParams("180", (True, True), (1, 1), (1, 2, 3, 4)),
    # LimParams("90", (False, True), (1, 1), (1, 2, 3, 4)),
    # LimParams("270", (False, True), (1, 1), (1, 2, 3, 4)),
    LimParams("NONE", (False, False), (1, 1), (1, 2, 3, 4)),
    LimParams("90", (True, False), (1, 1), (60, 70, 40, 30)),
    LimParams("90", (True, False), (1, 1), (0, 0, 10, 20)),
    LimParams("180", (False, True), (1, 1), (0, 0, 10, 20)),
    # LimParams("270", (True, True), (1, 1), (0, 0, 10, 20)),
    LimParams("270", (False, True), (1, 1), (0, 0, 1475, 195)),
    # LimParams("90", (True, False), (2, 2), (10, 20, 30, 40)),
    # LimParams("90", (True, False), (30, 30), (2, 3, 5, 6)),
]


# remark: there seems to be a problem with binning in the simulator
# when preloading an image


@pytest.mark.parametrize("lima_params", LimParamList2)
def test_lima_roi_nonsquare(beacon, lima_tmpdir, lima_simulator, lima_params):
    def array2img(arry, fpath):
        img = fabio.fabioimage.fabioimage(arry.astype("uint32"))
        idx = fpath.rfind(".")
        fmt = fpath[idx + 1 :]
        img.convert(fmt).save(fpath)

    ls = beacon.get("lima_simulator")

    # pilatus 300k w
    imagepath = str(lima_tmpdir) + "/image.edf"
    newimage = (numpy.random.rand(1475, 195) * 100).astype(numpy.uint32)
    array2img(newimage, imagepath)

    cc = ls._get_proxy("simulator")
    cc.mode = "LOADER_PREFETCH"
    cc.nb_prefetched_frames = 1
    cc.file_pattern = imagepath

    # manually update the changed image size in bliss
    ls._image_params._max_width, ls._image_params._max_height = (
        ls._image_params._tmp_get_max_width_height()
    )

    ls.proxy.image_flip = lima_params.flip
    ls.proxy.image_rotation = lima_params.rotation
    # ls.proxy.image_bin = lima_params.binning
    ls.proxy.image_roi = lima_params.roi
    ls.image.sync()

    _roi = ls.image.roi.to_array()
    _rot = ls.image.rotation
    _flip = ls.image.flip
    _bin = ls.image.binning

    ffrefroi = ls._image_params._calc_roi(_roi, _rot, _flip, _bin, inverse=True)

    # ls.proxy.image_bin = [1, 1]
    ls.proxy.image_flip = [False, False]
    ls.proxy.image_rotation = "None"

    assert all(ffrefroi == ls.proxy.image_roi)

    reverse = ls._image_params._calc_roi(
        ffrefroi, ls.image.rotation, ls.image.flip, ls.image.binning
    )
    assert all(reverse == numpy.array(lima_params.roi))


def test_lima_image_parameters(beacon, default_session, lima_simulator2, clean_gevent):
    clean_gevent["end-check"] = False
    cam = beacon.get("lima_simulator2")

    bv = beacon.get("bv1")

    fw, fh = 1024, 1024
    expo = 0.01
    bv.bpm.exposure = expo

    # First we align the ebv config and cam
    cam.image.flip = [False, False]
    bv.bpm.flip = [False, False]

    cam.image.rotation = 0
    bv.bpm.rotation = "NONE"

    cam.image.roi = [0, 0, fw, fh]
    bv.bpm.roi = [0, 0, fw, fh]

    cam.image.bin = [1, 1]
    bv.bpm.bin = [1, 1]

    assert list(cam.image.roi.to_array()) == [0, 0, fw, fh]
    assert bv.bpm.roi == [0, 0, fw, fh]

    assert cam.image.bin == [1, 1]
    assert bv.bpm.bin == [1, 1]

    assert cam.image.flip == [False, False]
    assert bv.bpm.flip == [False, False]

    assert cam.image.rotation == "NONE"
    assert bv.bpm.rotation == "NONE"

    # acquire images on cam and ebv and check they are equal
    s = ct(expo, cam)
    cam_img = s.get_data()["image"].get_last_image().data

    bv_img = bv.bpm._snap_and_get_image()

    assert numpy.array_equal(cam_img, bv_img)

    # define a centered subarea (image.roi) so flip should not modify roi coords
    w, h = fw / 2, fh / 2
    cam.image.roi = [fw / 2 - w / 2, fh / 2 - h / 2, w, h]

    cam.image.flip = [True, False]
    assert list(cam.image.roi.to_array()) == [fw / 2 - w / 2, fh / 2 - h / 2, w, h]

    cam.image.flip = [True, True]
    assert list(cam.image.roi.to_array()) == [fw / 2 - w / 2, fh / 2 - h / 2, w, h]

    cam.image.flip = [False, False]
    assert list(cam.image.roi.to_array()) == [fw / 2 - w / 2, fh / 2 - h / 2, w, h]

    # rotation 90 should invert x,y
    cam.image.rotation = 90
    assert list(cam.image.roi.to_array()) == [fh / 2 - h / 2, fw / 2 - w / 2, h, w]

    cam.image.rotation = 0
    assert list(cam.image.roi.to_array()) == [fw / 2 - w / 2, fh / 2 - h / 2, w, h]

    # modifying the cam config should not affected the ebv config since no scan has been done with cam yet
    assert bv.bpm.roi == [0, 0, fw, fh]

    # performing a scan with cam will affect ebv config because cam pushes its config to the tango server
    ct(0.01, cam)
    assert bv.bpm.roi == list(cam.image.roi.to_array())

    # modifying the ebv config should not affect a scan with cam
    # because cam will push its config which is stored in a BeaconObject

    bv.bpm.roi = [0, 0, fw, fh]
    bv_img = bv.bpm._snap_and_get_image()
    assert bv_img.shape == (fh, fw)

    s = ct(0.01, cam)
    cam_img = s.get_data()["image"].get_last_image().data
    assert cam_img.shape == (h, w)

    # play with binning
    cam.image.bin = [2, 2]
    assert list(cam.image.roi.to_array()) == [
        (fw / 2 - w / 2) / 2,
        (fh / 2 - h / 2) / 2,
        w / 2,
        h / 2,
    ]

    # print(cam.image.roi) => <128,128> <256 x 256>

    s = ct(0.01, cam)
    cam_img = s.get_data()["image"].get_last_image().data
    assert cam_img.shape == (h / 2, w / 2)

    bv.bpm.bin = [1, 1]
    bv.bpm.roi = [0, 0, fw, fh]
    bv.bpm.bin = [2, 2]

    cam.image.bin = [2, 2]
    cam.image.roi = [156, 181, 200, 150]
    # print(cam.image.bin)
    # print(cam.image.roi)
    # breakpoint()
    s = ct(0.01, cam)


def test_lima_image_bin_roi(beacon, default_session, lima_simulator):
    cam = beacon.get("lima_simulator")

    cam.image.bin = [2, 2]
    cam.image.roi = [156, 181, 200, 150]

    s = loopscan(1, 0.01, cam)

    cam_img = s.get_data()["image"].get_last_image().data
    assert cam_img.shape == (200, 150)

    with pytest.raises(AssertionError):
        cam.image.roi = [156, 181, 400, 150]
