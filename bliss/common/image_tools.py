# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


import fabio
import numpy as np
import matplotlib.pyplot as plt

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
        size = arry.shape[1], arry.shape[0]
        mode = _find_array_mode(arry.shape, arry.dtype)

    else:
        pil = Image.open(fpath)
        if pil.mode == "LA":
            pil = pil.convert("L")
        elif pil.mode == "I;16B":
            pil = pil.convert("I")

        mode = pil.mode
        size = pil.size
        data = pil.tostring()

        arry = buffer_to_array(mode, size, data)

    return (mode, size, arry)


def file_to_buffer(fpath):
    ext = fpath[fpath.rfind(".") + 1 :]
    if ext == "edf":
        arry = _fabio_file_to_array(fpath)
        data = arry.tostring()  # tobytes() ?
        size = arry.shape[1], arry.shape[0]
        mode = _find_array_mode(arry.shape, arry.dtype)

    else:
        pil = Image.open(fpath)
        if pil.mode == "LA":
            pil = pil.convert("L")
        elif pil.mode == "I;16B":
            pil = pil.convert("I")
        elif pil.mode == "P":
            pil = pil.convert("RGB")

        mode = pil.mode
        size = pil.size
        data = pil.tostring()

    return (mode, size, data)


def buffer_to_array(mode, size, data):
    w, h = size
    if mode == "RGB":
        return np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w, 3))
    elif mode == "RGBA":
        return np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w, 4))
    else:
        return np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w))


def pil_to_array(pil_img):
    w, h = pil_img.size
    mode = pil_img.mode
    data = pil_img.tostring()

    if mode == "RGB":
        arry = np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w, 3))
    elif mode == "RGBA":
        arry = np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w, 4))
    else:
        arry = np.frombuffer(data, NUMPY_MODES[mode]).reshape((h, w))

    return arry


def array_to_file(fpath, mode, arry):
    pil = Image.fromarray(arry, mode)
    ext = fpath[fpath.rfind(".") + 1 :]
    if ext == "edf":
        _fabio_array_to_file(arry, fpath)
    else:
        pil.save(fpath)


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


# ------ PLOT 2D ARRAY AS AN IMAGE ---------------------------


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
        if self._interactive:
            plt.pause(self._dtmin)
        else:
            plt.show()

    def close(self):
        plt.close()
        plt.ioff()


# ------ ARRAY CREATION  -----------------------


def empty_array(size, mode):
    w, h = size
    if mode == "RGBA":
        shape = (h, w, 4)
    elif mode == "RGB":
        shape = (h, w, 3)
    else:
        shape = (h, w)

    return np.empty(shape, NUMPY_MODES[mode])


def zero_array(size, mode):
    w, h = size
    if mode == "RGBA":
        shape = (h, w, 4)
    elif mode == "RGB":
        shape = (h, w, 3)
    else:
        shape = (h, w)

    return np.zeros(shape, NUMPY_MODES[mode])


def gauss2d(w, h, A=100, sx=10, sy=10, cx=0, cy=0):
    """ Create a 2D Gaussian array
        -  w: image width
        -  h: image height
        -  A: Gaussian amplitude (max)
        - sx: Gaussian sigma along x axis
        - sx: Gaussian sigma along y axis
        - cx: Gaussian position along x axis (centred by default)
        - cy: Gaussian position along y axis (centred by default)

    """

    cx += w / 2
    cy += h / 2

    x = np.linspace(0, w - 1, w)
    y = np.linspace(0, h - 1, h)
    x, y = np.meshgrid(x, y)

    return A * np.exp(
        -((x - cx) ** 2. / (2. * sx ** 2.) + (y - cy) ** 2. / (2. * sy ** 2.))
    )


# ------ DRAW IN ARRAY ------------------------


def DrawArc(arry, value=1, cx=0, cy=0, r1=100, r2=120, a1=0, a2=180):

    # check input args
    if r1 < 0 or r2 < 0:
        raise ValueError("radius must be a positive number !")
    if a1 < 0 or a2 < 0 or a1 > 360 or a2 > 360:
        raise ValueError("angles must be in [0, 360] degree !")

    h, w = arry.shape
    cx = w / 2 + cx
    cy = h / 2 + cy

    y, x = np.ogrid[:h, :w]

    # take the region between the 2 radius
    rmini = min(r1, r2)
    rmaxi = max(r1, r2)
    a = (x - cx) ** 2 + (y - cy) ** 2 <= rmaxi ** 2
    b = (x - cx) ** 2 + (y - cy) ** 2 >= rmini ** 2

    # take the region between the 2 angles
    # Numpy handles y/x where x[i] == 0  => inf   and   np.arctan(inf) ==> pi/2

    amini = min(a1, a2)
    amaxi = max(a1, a2)

    z = (y - cy) / (x - cx)

    if amini < 180 and amaxi > 180:
        c = np.arctan2(y - cy, x - cx) >= (amini * DEG2RAD)
        d = np.arctan2(y - cy, x - cx) <= (180 * DEG2RAD)

        amaxi -= 360
        e = np.arctan2(y - cy, x - cx) >= (-180 * DEG2RAD)
        f = np.arctan2(y - cy, x - cx) <= (amaxi * DEG2RAD)

        mask1 = a * b * c * d
        mask2 = a * b * e * f

        notmask1 = ~mask1
        notmask2 = ~mask2

        return arry * (notmask1 + notmask2) + value * (mask1 + mask2)

    else:

        if amini >= 180:
            amini -= 360
            amaxi -= 360

        c = np.arctan2(y - cy, x - cx) >= (amini * DEG2RAD)
        d = np.arctan2(y - cy, x - cx) <= (amaxi * DEG2RAD)

        mask = a * b * c * d

        notmask = ~mask

        return arry * notmask + mask * value


# ------ BUILD SPECIAL IMAGES ------------------


def create_beam_images(
    fdir,
    nframes=100,
    w=800,
    h=600,
    amp=1000.,
    centre=(0, 0),
    sigma=(100, 100),
    noise=0.1,
):

    """ Creates simulation images of a Gaussian beam with random background noise and random jitter on Gaussian parameters

        - fdir: a directory where to save images (e.g: '/home/beam_images' )
        - nframes: number of frames to generate
        - w: image width
        - h: image height
        - amp: maximum intensity of the Gaussian beam
        - centre: position (cx, cy) of the Gaussian beam (centred on image center by default)
        - sigma: sigma values (sx, sy) of the Gaussian beam
        - noise: noise level in perecentage of the Gaussian amplitude (%)


    """

    amp = min(amp, 2 ** 31)

    # generate random Gaussian parameters (centred + jitter)
    A = np.random.default_rng().normal(amp, 5, size=nframes)
    sx = np.random.default_rng().normal(sigma[0], 1, size=nframes)
    sy = np.random.default_rng().normal(sigma[1], 1, size=nframes)
    x0 = np.random.default_rng().normal(centre[0], 2, size=nframes)
    y0 = np.random.default_rng().normal(centre[1], 2, size=nframes)

    # generate beam images
    for i in range(nframes):
        bg = np.random.default_rng().normal(amp * noise, 10, size=(h, w))
        arry = gauss2d(w, h, A[i], sx[i], sy[i], x0[i], y0[i]) + bg

        # clip negative data
        mask = arry >= 0
        arry = mask * arry

        # convert to uint32
        arry = arry.astype("uint32")

        # save as image file (edf)
        fpath = f"{fdir}/frame_{i:04d}.edf"
        array_to_file(arry, fpath)


def create_ring_image(fpath, w=800, h=600, cx=0, cy=0, r1=100, r2=120, a1=0, a2=180):

    """" create arc """

    cx = w / 2 + cx
    cy = h / 2 + cy

    x = np.linspace(0, w - 1, w)
    y = np.linspace(0, h - 1, h)
    x, y = np.meshgrid(x, y)

    a = (x - cx) ** 2 + (y - cy) ** 2 >= r2 ** 2
    b = (x - cx) ** 2 + (y - cy) ** 2 <= r1 ** 2
    c = y >= h / 2
    r = (a + b + c) * 1
    r = r.astype("uint32")

    array_to_file(r, fpath)

    return r
