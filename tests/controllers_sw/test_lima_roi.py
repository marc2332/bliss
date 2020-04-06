import numpy
import pytest
import fabio

from collections import namedtuple

LimParams = namedtuple("LimParams", ["rotation", "flip", "binning", "roi"])

LimParamList = [
    LimParams("90", [True, False], [1, 1], [1, 2, 3, 4]),
    LimParams("180", [True, True], [1, 1], [1, 2, 3, 4]),
    LimParams("90", [False, True], [1, 1], [1, 2, 3, 4]),
    LimParams("270", [False, True], [1, 1], [1, 2, 3, 4]),
    LimParams("NONE", [False, False], [1, 1], [1, 2, 3, 4]),
    LimParams("90", [True, False], [1, 1], [600, 700, 400, 300]),
    LimParams("90", [True, False], [1, 1], [0, 0, 10, 20]),
    LimParams("180", [False, True], [1, 1], [0, 0, 10, 20]),
    LimParams("270", [True, True], [1, 1], [0, 0, 10, 20]),
    LimParams("270", [False, True], [1, 1], [0, 0, 1024, 1024]),
    LimParams("90", [True, False], [2, 2], [10, 20, 30, 40]),
    LimParams("90", [True, False], [30, 30], [2, 3, 5, 6]),
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
    LimParams("90", [True, False], [1, 1], [1, 2, 3, 4]),
    LimParams("180", [True, True], [1, 1], [1, 2, 3, 4]),
    # LimParams("90", [False, True], [1, 1], [1, 2, 3, 4]),
    # LimParams("270", [False, True], [1, 1], [1, 2, 3, 4]),
    LimParams("NONE", [False, False], [1, 1], [1, 2, 3, 4]),
    LimParams("90", [True, False], [1, 1], [60, 70, 40, 30]),
    LimParams("90", [True, False], [1, 1], [0, 0, 10, 20]),
    LimParams("180", [False, True], [1, 1], [0, 0, 10, 20]),
    # LimParams("270", [True, True], [1, 1], [0, 0, 10, 20]),
    LimParams("270", [False, True], [1, 1], [0, 0, 1475, 195]),
    # LimParams("90", [True, False], [2, 2], [10, 20, 30, 40]),
    # LimParams("90", [True, False], [30, 30], [2, 3, 5, 6]),
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
