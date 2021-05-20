# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import fabio
import numpy as np
from PIL import Image

NUMPY_MODES = {
    "L": np.uint8,
    "P": np.uint8,
    "RGB": np.uint8,
    "RGBA": np.uint8,
    "I;16": np.uint16,
    "I": np.int32,
    "F": np.float32,
    "RGB;32": np.int32,
}

DEG2RAD = np.pi / 180


# ------ LOAD AND SAVE IMAGES AS NUMPY ARRAY ----------------


def file_to_array(fpath):
    ext = fpath[fpath.rfind(".") + 1 :]
    if ext == "edf":
        arry = _fabio_file_to_array(fpath)
    else:
        pil = _file_to_pil(fpath)
        arry = pil_to_array(pil)

    return arry


def file_to_pil(fpath):
    ext = fpath[fpath.rfind(".") + 1 :]
    if ext == "edf":
        arry = _fabio_file_to_array(fpath)
        pil = array_to_pil(arry)
    else:
        pil = _file_to_pil(fpath)

    return pil


def file_to_buffer(fpath):
    ext = fpath[fpath.rfind(".") + 1 :]
    if ext == "edf":
        arry = _fabio_file_to_array(fpath)
        return array_to_buffer(arry)

    else:
        pil = _file_to_pil(fpath)
        return pil_to_buffer(pil)


def array_to_file(arry, fpath, mode=None):
    ext = fpath[fpath.rfind(".") + 1 :]
    if ext == "edf":
        _fabio_array_to_file(arry, fpath)
    else:
        if mode is None:
            mode = _find_array_mode(arry.shape, arry.dtype)
        pil = Image.fromarray(arry, mode)
        pil.save(fpath)


def array_to_pil(arry, mode=None):
    if mode is None:
        mode = _find_array_mode(arry.shape, arry.dtype)
    return Image.fromarray(arry, mode)


def array_to_buffer(arry, mode=None):
    if mode is None:
        mode = _find_array_mode(arry.shape, arry.dtype)
    size = arry.shape[1], arry.shape[0]
    data = arry.tostring()
    return (mode, size, data)


def pil_to_file(pil, fpath):
    pil.save(fpath)


def pil_to_array(pil):
    return buffer_to_array(*pil_to_buffer(pil))


def pil_to_buffer(pil):
    if hasattr(pil, "tostring"):
        data = pil.tostring()  # PIL
    else:
        data = pil.tobytes()  # PILOW
    return (pil.mode, pil.size, data)


def buffer_to_file(mode, size, data, fpath):
    arry = buffer_to_array(mode, size, data)
    array_to_file(arry, fpath)


def buffer_to_array(mode, size, data):
    w, h = size
    if mode == "RGB":
        return np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w, 3))
    elif mode == "RGBA":
        return np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w, 4))
    else:
        return np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w))


def buffer_to_pil(mode, size, data):
    arry = buffer_to_array(mode, size, data)
    return array_to_pil(arry)


def _fabio_array_to_file(arry, fpath):
    ftype = fpath.split(".")[-1]
    img = fabio.fabioimage.fabioimage(arry)
    img.convert(ftype).save(fpath)


def _fabio_file_to_array(fpath):
    return fabio.open(fpath).data


def _find_array_mode(shape, dtype):

    if len(shape) == 2:

        if dtype == np.uint8:
            return "L"
        elif dtype == np.uint16:
            return "I;16"
        elif dtype == np.int32:
            return "I"
        elif dtype == np.float32:
            return "F"

    elif len(shape) == 3:
        if shape[2] == 3:
            if dtype == np.uint8:
                return "RGB"
            elif dtype == np.int32:
                return "RGB;32"
        elif shape[2] == 4:
            if dtype == np.uint8:
                return "RGBA"

    raise ValueError(
        f"cannot find a suitable mode for an array with shape {shape} and dtype {dtype}"
    )


def _file_to_pil(fpath, raw=False):
    pil = Image.open(fpath)
    if not raw:
        if pil.mode == "LA":
            pil = pil.convert("L")
        elif pil.mode == "I;16B":
            pil = pil.convert("I")
        elif pil.mode == "P":
            pil = pil.convert("RGB")
    return pil


# ------ ARRAY CREATION  -----------------------


def gauss2d(w, h, A=100, sx=10, sy=10, cx=None, cy=None):
    """ Create a 2D Gaussian array
        -  w: image width
        -  h: image height
        -  A: Gaussian amplitude (max)
        - sx: Gaussian sigma along x axis
        - sx: Gaussian sigma along y axis
        - cx: Gaussian center along x axis (image center by default)
        - cy: Gaussian center along y axis (image center by default)

    """
    if cx is None:
        cx = w / 2

    if cy is None:
        cy = h / 2

    x = np.linspace(0, w - 1, w)
    y = np.linspace(0, h - 1, h)
    x, y = np.meshgrid(x, y)

    return A * np.exp(
        -((x - cx) ** 2. / (2. * sx ** 2.) + (y - cy) ** 2. / (2. * sy ** 2.))
    )


def arcmask(w, h, cx, cy, r1, r2, a1, a2):
    x = np.linspace(0, w - 1, w)
    y = np.linspace(0, h - 1, h)
    x, y = np.meshgrid(x, y)

    radius = (x - cx) ** 2 + (y - cy) ** 2
    c1 = (radius >= r1 ** 2) * (radius <= r2 ** 2)

    angles = (np.arctan2((y - cy), (x - cx)) / DEG2RAD) % 360
    c2 = (angles >= a1) * (angles <= a2)

    return c1 * c2


# ------ DRAW IN ARRAY ------------------------
def draw_rect(arry, x, y, w, h, fill_value=0):
    arry[y : y + h, x : x + w] = fill_value
    return arry


def draw_arc(arry, cx, cy, r1, r2, a1, a2, fill_value=0):

    """" draw circular arc """

    h, w = arry.shape[0:2]
    mask = arcmask(w, h, cx, cy, r1, r2, a1, a2)
    return np.where(
        mask, fill_value, arry
    )  # where True in mask use fill_value else arry


# ------ BUILD SPECIAL IMAGES ------------------


def test_image(w=800, h=600):

    arry = np.ones((h, w))
    arry = draw_rect(
        arry, int(w * 0.1), int(h * 0.1), int(w * 0.1), int(h * 0.1), fill_value=0
    )
    arry = draw_rect(
        arry, int(w * 0.5), int(h * 0.1), int(w * 0.15), int(h * 0.15), fill_value=50
    )
    arry = draw_rect(
        arry, int(w * 0.1), int(h * 0.5), int(w * 0.2), int(h * 0.2), fill_value=100
    )
    arry = draw_rect(
        arry, int(w * 0.5), int(h * 0.5), int(w * 0.25), int(h * 0.25), fill_value=150
    )

    return arry.astype("uint8")


def create_beam_images(
    nframes=10,
    w=800,
    h=600,
    amp=1000.,
    centre=(None, None),
    sigma=(100, 100),
    noise=0.1,
):

    """ Creates simulation images of a Gaussian beam with random background noise and random jitter on Gaussian parameters

        - fdir: a directory where to save images (e.g: '/home/beam_images' )
        - nframes: number of frames to generate
        - w: image width
        - h: image height
        - amp: maximum intensity of the Gaussian beam
        - centre: position (cx, cy) of the Gaussian beam (image center by default)
        - sigma: sigma values (sx, sy) of the Gaussian beam
        - noise: noise level in perecentage of the Gaussian amplitude (%)


    """
    # centre by default
    cx, cy = centre
    if cx is None:
        cx = w / 2
    if cy is None:
        cy = h / 2

    # generate random Gaussian parameters (centred + jitter)
    A = np.random.default_rng().normal(amp, 5, size=nframes)
    sx = np.random.default_rng().normal(sigma[0], 1, size=nframes)
    sy = np.random.default_rng().normal(sigma[1], 1, size=nframes)
    x0 = np.random.default_rng().normal(cx, 2, size=nframes)
    y0 = np.random.default_rng().normal(cy, 2, size=nframes)

    # generate beam images
    frames = []
    for i in range(nframes):
        bg = np.random.default_rng().normal(amp * noise, 10, size=(h, w))
        arry = gauss2d(w, h, A[i], sx[i], sy[i], x0[i], y0[i]) + bg

        # clip negative data
        mask = arry >= 0
        arry = mask * arry

        # convert to uint32
        arry = arry.astype("uint32")

        frames.append(arry)

    return frames


# ----- PLOT IMAGE ----------------------


def get_image_display(interactive=True, dtmin=0.001, defsize=(800, 600)):
    """  Plot 2D array as an image (static or live update) """

    import matplotlib.pyplot as plt

    class Display:
        def __init__(self, interactive=True, dtmin=0.001, defsize=(800, 600)):
            self._interactive = interactive
            self._dtmin = dtmin

            if interactive:
                plt.ion()
            else:
                plt.ioff()

            self.plot = plt.imshow(np.zeros((defsize[1], defsize[0])))
            plt.pause(self._dtmin)

        def __del__(self):
            plt.close()
            plt.ioff()

        def show(self, arry):
            try:
                plt.cla()  # clear axes
                # plt.clf()   # clear figure
            except Exception:
                pass

            self.plot = plt.imshow(arry)
            plt.pause(self._dtmin)

            if not self._interactive:
                plt.show()

        def close(self):
            plt.close()
            plt.ioff()

    return Display(interactive, dtmin, defsize)
