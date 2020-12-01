import os
import pytest
import numpy
import time
import gevent
from bliss.common.scans import ct
from bliss.controllers.lima.limatools import (
    load_simulator_frames,
    reset_cam,
    get_last_image,
)

from bliss.data.lima_image import image_from_server
from bliss.shell.formatters.table import IncrementalTable

from bliss.common.image_tools import get_image_display


# --- Notes about rect vs roi ------------
# rect = [left, top, right, bottom]
# roi  = [left, top, width, height] = [left, top, right-left, bottom-top]


# ---- These tests are using images from 'images_directory' (bliss/tests/images) -----------------------------------------------
#
# chart_1.edf => size = (200,150) with bg @ 255
#             => rect = [30, 10, 80, 50]   @ 0  <=> roi = [30, 10, 50, 40]
#             => rect = [90, 60, 140, 110] @ 1  <=> roi = [90, 60, 50, 50]
#
# chart_2.edf => size = (600,600) with bg @ 255
#             => rect = [160, 60, 280, 260]  <=> roi = [160, 60, 120, 200]   (roi around 'UP_ARROW' => asum = 21843)
#
# chart_3.edf => size = (200,100)


def test_lima_basic_1(beacon, default_session, lima_simulator, images_directory):

    """
    =================== TEST lima-core 1.9.4 =============================
        with :
        lima-camera-simulator     1.9.2            py37h6bb024c_0    esrf-bcu
        lima-camera-simulator-tango 1.9.2                         0    esrf-bcu
        lima-core                 1.9.4           py37_debugh6bb024c_0    esrf-bcu
        lima-tango-server         1.9.6                         0    esrf-bcu

        -------------------- test without bliss pushing its updated-roi ------------
        we let the proxy updating the roi (bliss doesn't push the roi, the roi is set directly at proxy level)
        
        1) If bliss pushes acq_params in this order: flip->rot->bin->roi: TEST FAILED
        (independent from 'set back binning to 1,1 before ...')

            width:    100
            height:   200
            depth:    4
            bpp:      Bpp32
            binning:  [1, 1]
            flip:     [False, False]
            rotation: 90
            roi:      [0, 0, 100, 200]

            === SET PROXY PARAMS image_flip = [False, False] (from [False False]) (proxy.roi = [  0   0 200 100])
            === SET PROXY PARAMS image_rotation = 90 (from NONE) (proxy.roi = [  0   0 200 100])
            === SET PROXY PARAMS image_bin = [1, 1] (from [1 1]) (proxy.roi = [  0   0 100 200])
                Exception(InvalidValue): Roi out of limitsm_max_roi=<0,0>-<200x100>, roi=<0,0>-<100x200>

        
        2) If bliss pushes acq_params in this order: bin->flip->rot->roi: TEST PASSED
        (independent from 'set back binning to 1,1 before ...')


    =================== TEST lima-core 1.9.6 =============================
        with :
        lima-camera-simulator     1.9.2            py37h6bb024c_0    esrf-bcu
        lima-camera-simulator-tango 1.9.2                         0    esrf-bcu
        lima-core                 1.9.6           
        lima-tango-server         1.9.6                         0    esrf-bcu

        -------------------- test without bliss pushing its updated-roi ------------
        we let the proxy updating the roi (bliss doesn't push the roi, the roi is set directly at proxy level)
        
        1) If bliss pushes acq_params in this order: flip->rot->bin->roi: TEST FAILED

            width:    100
            height:   200
            depth:    4
            bpp:      Bpp32
            binning:  [1, 1]
            flip:     [False, False]
            rotation: 90
            roi:      [0, 0, 100, 200]

            === SET PROXY PARAMS image_flip = [False, False] (from [False False]) (proxy.roi = [  0   0 200 100])
            === SET PROXY PARAMS image_rotation = 90 (from NONE) (proxy.roi = [  0   0 200 100])
            === SET PROXY PARAMS image_bin = [1, 1] (from [1 1]) (proxy.roi = [  0   0 200 100])
                Exception(InvalidValue): Roi out of limitsm_max_roi=<0,0>-<100x200>, roi=<0,0>-<200x100>
        
        2) If bliss pushes acq_params in this order: bin->flip->rot->roi: TEST PASSED


    =================== TEST lima-core 1.9.7rc1 =============================
        with :
        lima-camera-simulator     1.9.2            py37h6bb024c_0    esrf-bcu
        lima-camera-simulator-tango 1.9.2                         0    esrf-bcu
        lima-core                 1.9.7rc1           
        lima-tango-server         1.9.6                         0    esrf-bcu

        -------------------- test without bliss pushing its updated-roi ------------
        we let the proxy updating the roi (bliss doesn't push the roi, the roi is set directly at proxy level)
        
        1) If bliss pushes acq_params in this order: flip->rot->bin->roi: TEST PASSED
        (independent from 'set back binning to 1,1 before ...')
        
        2) If bliss pushes acq_params in this order: bin->flip->rot->roi: TEST PASSED
        (independent from 'set back binning to 1,1 before ...')


    """
    # ---Load camera and test image
    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_3.edf")
    load_simulator_frames(cam, 1, img_path)
    print(cam.image.__info__())
    s = ct(0.01, cam)


def test_lima_basic_2(beacon, default_session, lima_simulator, images_directory):

    """
    =================== TEST lima-core 1.9.4 =============================
        with :
        lima-camera-simulator     1.9.2            py37h6bb024c_0    esrf-bcu
        lima-camera-simulator-tango 1.9.2                         0    esrf-bcu
        lima-core                 1.9.4           py37_debugh6bb024c_0    esrf-bcu
        lima-tango-server         1.9.6                         0    esrf-bcu

        -------------------- test without bliss pushing its updated-roi ------------
        we let the proxy updating the roi (bliss doesn't push the roi, the roi is set directly at proxy level)
        
        1) If bliss pushes acq_params in this order: flip->rot->bin->roi: TEST FAILED
        (independent from 'set back binning to 1,1 before ...')

            width:    99
            height:   199
            depth:    4
            bpp:      Bpp32
            binning:  [1, 1]
            flip:     [False, False]
            rotation: 90
            roi:      [1, 0, 99, 199]

            === SET PROXY PARAMS image_flip = [False, False] (from [False False]) (proxy.roi = [  0   0 199  99])
            === SET PROXY PARAMS image_rotation = 90 (from NONE) (proxy.roi = [  0   0 199  99])
                Exception(InvalidValue): Roi out of limitsm_max_roi=<0,0>-<200x100>, roi=<1,0>-<99x199>
            
        
        2) If bliss pushes acq_params in this order: bin->flip->rot->roi: TEST FAILED
        (independent from 'set back binning to 1,1 before ...')

            width:    99
            height:   199
            depth:    4
            bpp:      Bpp32
            binning:  [1, 1]
            flip:     [False, False]
            rotation: 90
            roi:      [1, 0, 99, 199]

            === SET PROXY PARAMS image_bin = [1, 1] (from [1 1]) (proxy.roi = [  0   0 199  99])
            === SET PROXY PARAMS image_flip = [False, False] (from [False False]) (proxy.roi = [  0   0 199  99])
            === SET PROXY PARAMS image_rotation = 90 (from NONE) (proxy.roi = [  0   0 199  99])
                Exception(InvalidValue): Roi out of limitsm_max_roi=<0,0>-<200x100>, roi=<1,0>-<99x199>

                BUT basic_1 PASSED !

    
    =================== TEST lima-core 1.9.6 =============================
        with :
        lima-camera-simulator     1.9.2            py37h6bb024c_0    esrf-bcu
        lima-camera-simulator-tango 1.9.2                         0    esrf-bcu
        lima-core                 1.9.6           py37_debugh6bb024c_0    esrf-bcu
        lima-tango-server         1.9.6                         0    esrf-bcu

        -------------------- test without bliss pushing its updated-roi ------------
        we let the proxy updating the roi (bliss doesn't push the roi, the roi is set directly at proxy level)
        
        1) If bliss pushes acq_params in this order: flip->rot->bin->roi: TEST PASSED
        
        2) If bliss pushes acq_params in this order: bin->flip->rot->roi: TEST PASSED

    
    =================== TEST lima-core 1.9.7rc1 ==========================
        with :
        lima-camera-simulator     1.9.2            py37h6bb024c_0    esrf-bcu
        lima-camera-simulator-tango 1.9.2                         0    esrf-bcu
        lima-core                 1.9.7rc1
        lima-tango-server         1.9.6                         0    esrf-bcu

        -------------------- test without bliss pushing its updated-roi ------------
        we let the proxy updating the roi (bliss doesn't push the roi, the roi is set directly at proxy level)
        
        1) If bliss pushes acq_params in this order: flip->rot->bin->roi: TEST PASSED
        (independent from 'set back binning to 1,1 before ...')

        
        2) If bliss pushes acq_params in this order: bin->flip->rot->roi: TEST PASSED
        (independent from 'set back binning to 1,1 before ...')

    """
    # ---Load camera and test image
    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_3.edf")
    load_simulator_frames(cam, 1, img_path)
    cam.image.rotation = 0
    cam.image.roi = [0, 0, 199, 99]
    cam.image.rotation = 90
    cam.proxy.image_roi = [
        0,
        0,
        199,
        99,
    ]  # without rotation because proxy not rotated yet
    print(cam.image.__info__())
    s = ct(0.01, cam)
    assert list(cam.proxy.image_roi) == cam.image.roi


@pytest.mark.skip()  # test failing with lima-core<=1.9.6
def test_lima_basic_3(beacon, default_session, lima_simulator, images_directory):

    # ---Load camera and test image
    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_1.edf")
    load_simulator_frames(cam, 1, img_path)
    print(cam.image.__info__())

    expo = 0.01
    s = ct(expo, cam)

    reset_cam(cam)

    roi1 = [30, 10, 50, 40]
    roi2 = [90, 60, 50, 50]

    # select roi1 (full of zeros)
    cam.image.roi = roi1
    s = ct(expo, cam)
    a = get_last_image(cam)
    assert numpy.sum(a) == 0

    # select roi2 (full of ones)
    cam.image.roi = roi2
    s = ct(expo, cam)
    a = get_last_image(cam)
    assert numpy.sum(a) == roi2[2] * roi2[3]

    w0, h0 = cam.image._get_detector_max_size()
    cam.image.rotation = 0
    cam.image.roi = 0, 0, 0, 0
    assert cam.image.roi == [0, 0, w0, h0]
    assert cam.image.raw_roi == [0, 0, w0, h0]
    assert cam.image.fullsize == (w0, h0)
    s = ct(expo, cam)

    cam.image.rotation = 90
    cam.image.roi = 0, 0, 0, 0
    assert cam.image.roi == [0, 0, h0, w0]
    assert cam.image.raw_roi == [0, 0, w0, h0]
    assert cam.image.fullsize == (h0, w0)
    s = ct(expo, cam)

    cam.image.rotation = 0
    assert cam.image.roi == [0, 0, w0, h0]
    assert cam.image.raw_roi == [0, 0, w0, h0]
    assert cam.image.fullsize == (w0, h0)
    s = ct(expo, cam)


def test_lima_image_1(beacon, default_session, lima_simulator, images_directory):
    """ Perform a serie of tests using a Bliss Lima detector in different geometries.
        The value of the sum of a given roi on the lima image is checked for different combination
        of {binning, flipping, rotation}.
        The way the image_array (corresponding to the roi) is obtained is defined by the 'data_mode' in [0, 1, 2] (see 'get_image_array').
        The order of the commands sent to the proxy (for bin, flip, rot) is fixed and defined in bliss.lima_base.apply_parameters ('bfr').

        with _DEBUG == 0 => No prints, No Image Display, exit at first wrong sum
        with _DEBUG == 1 => Tabulated prints, No Image Display
        with _DEBUG == 2 => Tabulated prints, Image Display

    """
    _DEBUG = 0

    if _DEBUG > 1:
        # ---Activate a live display for debug
        disp = get_image_display()

    else:
        disp = None

    # --- Define test params
    expo = 0.001
    roi1 = [160, 60, 120, 200]

    binvals = [[1, 1], [2, 2], [4, 4]]  # , [4, 4]] [1, 2], , [2, 1]
    rotvals = [0, 90, 180, 270]
    flipvals = [
        [False, False],
        [True, True],
        [True, False],
        [False, True],
    ]  # [True, False], [False, True]
    data_modes = [0]  # 1, 2, 3
    push_modes = ["bfr"]  # 'bfr','frb','rbf'

    _BPP2DTYPE = {
        "Bpp8": "uint8",
        "Bpp8S": "int8",
        "Bpp10": "uint16",
        "Bpp10S": "int16",
        "Bpp12": "uint16",
        "Bpp12S": "int16",
        "Bpp14": "uint16",
        "Bpp14S": "int16",
        "Bpp16": "uint16",
        "Bpp16S": "int16",
        "Bpp32": "uint32",
        "Bpp32S": "int32",
        "Bpp32F": "float32",
    }

    last_params = {"bin": None, "flip": None, "rot": None, "roi": None}

    # ---Load camera and test image 'chart_2.edf' (600,600) with bg @ 255
    #  => roi = [160, 60, 120, 200] ( <=> rect=[160, 60, 280, 260] <=> roi around 'UP_ARROW' => asum = 21843)
    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_2.edf")
    load_simulator_frames(cam, 1, img_path)

    def push_params(bin, flip, rot, push_mode="bfr", cache=False):

        try:

            if push_mode == "bfr":
                if cache:
                    if bin != last_params["bin"]:
                        cam.image.binning = bin
                        last_params["bin"] = bin

                    if flip != last_params["flip"]:
                        cam.image.flip = flip
                        last_params["flip"] = flip

                    if rot != last_params["rot"]:
                        cam.image.rotation = rot
                        last_params["rot"] = rot
                else:
                    cam.image.binning = bin
                    cam.image.flip = flip
                    cam.image.rotation = rot

            elif push_mode == "frb":
                if cache:
                    if flip != last_params["flip"]:
                        cam.image.flip = flip
                        last_params["flip"] = flip

                    if rot != last_params["rot"]:
                        cam.image.rotation = rot
                        last_params["rot"] = rot

                    if bin != last_params["bin"]:
                        cam.image.binning = bin
                        last_params["bin"] = bin

                else:
                    cam.image.flip = flip
                    cam.image.rotation = rot
                    cam.image.binning = bin

            elif push_mode == "rbf":
                if cache:
                    if rot != last_params["rot"]:
                        cam.image.rotation = rot
                        last_params["rot"] = rot

                    if bin != last_params["bin"]:
                        cam.image.binning = bin
                        last_params["bin"] = bin

                    if flip != last_params["flip"]:
                        cam.image.flip = flip
                        last_params["flip"] = flip

                else:
                    cam.image.rotation = rot
                    cam.image.binning = bin
                    cam.image.flip = flip

        except Exception as e:
            if _DEBUG > 0:
                print(
                    f"Error in PushParams: bin={bin}, flip={flip}, rot={rot}, push_mode={push_mode} "
                )
                raise e

    def get_image_sizes():
        _bpp = str(cam.proxy.image_type)
        _sizes = cam.proxy.image_sizes
        _shape = int(_sizes[3]), int(_sizes[2])
        _depth = int(_sizes[1])
        _sign = int(_sizes[0])
        _dtype = _BPP2DTYPE[_bpp]
        _dlen = _shape[0] * _shape[1] * _depth

        return _dlen, _dtype, _shape

    def get_image_array(data_mode=0, scan=None):

        if data_mode == 0:
            return get_last_image(cam)

        elif data_mode == 1:
            data_type, data = cam.proxy.last_image
            if data_type == "DATA_ARRAY":
                _dlen, _dtype, _shape = get_image_sizes()
                return numpy.frombuffer(data[-_dlen:], dtype=_dtype).reshape(_shape)
            else:
                raise TypeError(f"cannot handle data-type {data_type}")

        elif data_mode == 2:
            return image_from_server(cam.proxy, -1)

        elif data_mode == 3:
            return scan.get_data("image").as_array()

    def check(binning, flip, rotation, data_mode, push_mode):

        push_params(binning, flip, rotation, push_mode, cache=False)

        s = ct(expo, cam)

        img = get_image_array(data_mode, s)

        if disp:
            disp.show(img)

        if _DEBUG == 0:
            assert numpy.sum(img) == asum
        else:
            if numpy.sum(img) == asum:
                res = "PASSED"
            else:
                res = "FAILED"

            # broi = cam.image.roi
            # proi = list(cam.proxy.image_roi)

            line = [
                counts,
                binning,
                [int(i) for i in flip],
                rotation,
                data_mode,
                push_mode,
                res,
                # broi,
                # proi,
            ]
            line = tab.add_line(line)
            print(line)

    # ---Prepare camera
    push_params([1, 1], [False, False], 0, push_mode="bfr")
    cam.image.roi = roi1
    cam.proxy.image_roi = roi1

    s = ct(expo, cam)

    assert list(cam.proxy.image_bin) == [1, 1]
    assert list(cam.proxy.image_flip) == [False, False]
    assert cam.proxy.image_rotation == "NONE"
    assert list(cam.proxy.image_roi) == roi1

    # ---Get the sum of the roi
    for mode in range(4):
        a = get_image_array(mode, s)
        asum = numpy.sum(a)
        assert asum == 21843

    # ---Apply the different combinations and permutations of (bin, flip, rot)

    counts = 0

    if _DEBUG > 0:
        labels = [
            "geoid",
            "binning",
            "flipping",
            "rotation",
            "data_mode",
            "push_mode",
            "result",
            # "       bliss roi       ",
            # "       proxy roi       ",
        ]
        tab = IncrementalTable([labels], col_sep="|")
        tab.resize(minwidth=10, maxwidth=30)
        tab.add_separator(sep="-", line_index=1)
        tab.set_column_params(0, {"push_mode": "", "dtype": "d"})
        tab.set_column_params(3, {"push_mode": "", "dtype": "d"})
        tab.set_column_params(4, {"push_mode": "", "dtype": "d"})
        print(f"\n{tab}")

    for binning in binvals:
        for flip in flipvals:
            for rotation in rotvals:
                for data_mode in data_modes:
                    for push_mode in push_modes:
                        check(binning, flip, rotation, data_mode, push_mode)
                        counts += 1

                if _DEBUG > 0:
                    tab.add_separator(sep="-")

    if disp:
        disp.close()

    # if "FAILED" in [str(x).strip() for x in tab.get_column(6)]:
    #    assert False


def test_lima_proxy_1(beacon, default_session, lima_simulator, images_directory):
    """ Perform a serie of tests using a Lima proxy.image in different geometries.
        The value of the sum of a given roi on the lima image is checked for different combination
        of {binning, flipping, rotation}.
        The way the image_array (corresponding to the roi) is obtained is defined by the 'data_mode' in [0, 1, 2] (see 'get_image_array').
        The order of the commands sent to the proxy (for bin, flip, rot) is defined by the 'push_mode' in ['bfr', 'frb'] (see 'push_params')

        with _DEBUG == 0 => No prints, No Image Display, exit at first wrong sum
        with _DEBUG == 1 => Tabulated prints, No Image Display
        with _DEBUG == 2 => Tabulated prints, Image Display


        ===== NOTES ABOUT lima-core versions ==========================

        - bin=[2, 2] + rot=90 + push_mode=frb    breaks lima-core <= 1.9.4
        - bin=[2, 2] + push_mode=bfr             breaks lima-core <= 1.9.4
        - bin=[1, 2] + rot=90 or 270             breaks lima-core <= 1.9.6 (and 1.9.7rc1) (rot 0 and 180 ok)
        - data_mode = 1 or 2  + rotation!=0      breaks lima-core <= 1.9.6 (and 1.9.7rc1) (independant from flip and bin)

    """
    _DEBUG = 0

    if _DEBUG > 1:
        # ---Activate a live display for debug
        disp = get_image_display()

    else:
        disp = None

    # --- Define test params
    expo = 0.001
    roi1 = [160, 60, 120, 200]

    binvals = [[1, 1], [2, 2]]  # , [4, 4]] [1, 2], , [2, 1]
    rotvals = ["NONE", "90", "180", "270"]  # "180", "270"
    flipvals = [
        [False, False],
        [True, True],
        [True, False],
        [False, True],
    ]  # [True, False], [False, True]
    data_modes = [0]  # 1, 2
    push_modes = ["bfr"]  # 'frb','bfr'

    _BPP2DTYPE = {
        "Bpp8": "uint8",
        "Bpp8S": "int8",
        "Bpp10": "uint16",
        "Bpp10S": "int16",
        "Bpp12": "uint16",
        "Bpp12S": "int16",
        "Bpp14": "uint16",
        "Bpp14S": "int16",
        "Bpp16": "uint16",
        "Bpp16S": "int16",
        "Bpp32": "uint32",
        "Bpp32S": "int32",
        "Bpp32F": "float32",
    }

    last_params = {"bin": None, "flip": None, "rot": None, "roi": None}

    # ---Load camera and test image 'chart_2.edf' (600,600) with bg @ 255
    #  => roi = [160, 60, 120, 200] ( <=> rect=[160, 60, 280, 260] <=> roi around 'UP_ARROW' => asum = 21843)
    cam = beacon.get("lima_simulator")
    img_path = os.path.join(str(images_directory), "chart_2.edf")
    load_simulator_frames(cam, 1, img_path)

    cam.proxy.acq_mode = "SINGLE"
    cam.proxy.acq_trigger_mode = "INTERNAL_TRIGGER"
    cam.proxy.acq_nb_frames = 1
    cam.proxy.acq_expo_time = expo
    cam.proxy.video_source = "LAST_IMAGE"
    cam.proxy.video_active = True

    def push_params(bin, flip, rot, push_mode="bfr", cache=False):

        try:

            if push_mode == "bfr":
                if cache:
                    if bin != last_params["bin"]:
                        cam.proxy.image_bin = bin
                        last_params["bin"] = bin

                    if flip != last_params["flip"]:
                        cam.proxy.image_flip = flip
                        last_params["flip"] = flip

                    if rot != last_params["rot"]:
                        cam.proxy.image_rotation = rot
                        last_params["rot"] = rot
                else:
                    cam.proxy.image_bin = bin
                    cam.proxy.image_flip = flip
                    cam.proxy.image_rotation = rot

            elif push_mode == "frb":
                if cache:
                    if flip != last_params["flip"]:
                        cam.proxy.image_flip = flip
                        last_params["flip"] = flip

                    if rot != last_params["rot"]:
                        cam.proxy.image_rotation = rot
                        last_params["rot"] = rot

                    if bin != last_params["bin"]:
                        cam.proxy.image_bin = bin
                        last_params["bin"] = bin

                else:
                    cam.proxy.image_flip = flip
                    cam.proxy.image_rotation = rot
                    cam.proxy.image_bin = bin

        except Exception as e:
            if _DEBUG > 0:
                print(
                    f"Error in PushParams: bin={bin}, flip={flip}, rot={rot}, push_mode={push_mode} "
                )
                raise e

    def set_roi(roi):
        if roi != last_params["roi"]:
            cam.proxy.image_roi = roi
            last_params["roi"] = roi

    def snap():
        cam.proxy.prepareAcq()
        cam.proxy.startAcq()
        gevent.sleep(expo)
        with gevent.Timeout(2.0):
            while cam.proxy.last_image_ready == -1:
                gevent.sleep(0.001)

    def get_image_sizes():
        _bpp = str(cam.proxy.image_type)
        _sizes = cam.proxy.image_sizes
        _shape = int(_sizes[3]), int(_sizes[2])
        _depth = int(_sizes[1])
        _sign = int(_sizes[0])
        _dtype = _BPP2DTYPE[_bpp]
        _dlen = _shape[0] * _shape[1] * _depth

        return _dlen, _dtype, _shape

    def get_image_array(data_mode=0):

        if data_mode == 0:
            return get_last_image(cam)

        elif data_mode == 1:
            data_type, data = cam.proxy.last_image
            if data_type == "DATA_ARRAY":
                _dlen, _dtype, _shape = get_image_sizes()
                return numpy.frombuffer(data[-_dlen:], dtype=_dtype).reshape(_shape)
            else:
                raise TypeError(f"cannot handle data-type {data_type}")

        elif data_mode == 2:
            return image_from_server(cam.proxy, -1)

    def check(binning, flip, rotation, data_mode, push_mode):

        push_params(binning, flip, rotation, push_mode, cache=False)

        snap()

        img = get_image_array(data_mode)

        if disp:
            disp.show(img)

        if _DEBUG == 0:
            assert numpy.sum(img) == asum
        else:
            if numpy.sum(img) == asum:
                res = "PASSED"
            else:
                res = "FAILED"

            line = [
                counts,
                binning,
                [int(i) for i in flip],
                rotation,
                data_mode,
                push_mode,
                res,
            ]
            line = tab.add_line(line)
            print(line)

    # ---Prepare camera
    push_params([1, 1], [False, False], "NONE", push_mode="bfr")
    set_roi(roi1)

    assert list(cam.proxy.image_bin) == [1, 1]
    assert list(cam.proxy.image_flip) == [False, False]
    assert cam.proxy.image_rotation == "NONE"
    assert list(cam.proxy.image_roi) == roi1

    # ---Get the sum of the roi
    snap()
    for mode in range(3):
        a = get_image_array(mode)
        asum = numpy.sum(a)
        assert asum == 21843

    # ---Apply the different combinations of (bin, flip, rot)
    counts = 0

    if _DEBUG > 0:
        labels = [
            "geoid",
            "binning",
            "flipping",
            "rotation",
            "data_mode",
            "push_mode",
            "result",
        ]
        tab = IncrementalTable([labels], col_sep="|")
        tab.resize(minwidth=10, maxwidth=30)
        tab.add_separator(sep="-", line_index=1)
        tab.set_column_params(0, {"push_mode": "", "dtype": "d"})
        tab.set_column_params(4, {"push_mode": "", "dtype": "d"})
        print(f"\n{tab}")

    for binning in binvals:
        for flip in flipvals:
            for rotation in rotvals:
                for data_mode in data_modes:
                    for push_mode in push_modes:
                        check(binning, flip, rotation, data_mode, push_mode)
                        counts += 1

                if _DEBUG > 0:
                    tab.add_separator(sep="-")

    if disp:
        disp.close()

    # if "FAILED" in [str(x).strip() for x in tab.get_column(6)]:
    #    assert False
