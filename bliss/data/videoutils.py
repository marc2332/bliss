from __future__ import absolute_import

__authors__ = ["D. Naudet"]
__license__ = ""
__date__ = "01/09/2017"


import cv2
import numpy as np

from Lima import Core


opencv_code = {
    Core.I420: cv2.COLOR_YUV2RGB_I420,
    Core.RGB24: None,
    Core.BGR24: cv2.COLOR_BGR2RGB,
    Core.Y8: None,  # cv2.COLOR_GRAY2RGB,
    Core.Y16: None,  # cv2.COLOR_GRAY2RGB,
    Core.Y32: None,
    Core.BAYER_BG16: cv2.COLOR_BayerRG2RGB,  # cv2.COLOR_BayerBG2RGB,
    Core.BAYER_BG8: cv2.COLOR_BayerRG2RGB,  # cv2.COLOR_BayerBG2RGB,
    Core.BAYER_RG16: cv2.COLOR_BayerRG2BGR,
    Core.BAYER_RG8: cv2.COLOR_BayerRG2BGR,
    Core.YUV422PACKED: cv2.COLOR_YUV2RGB_Y422,
}


def _decode_video(buf, dst_code):
    return cv2.cvtColor(buf, dst_code)


def _scale_to_8bits(array, in_bits=None):
    if in_bits is None:
        in_bits = 8 * array.dtype.itemsize

    shift = in_bits - 8

    if shift > 0:
        array = np.right_shift(array, shift).astype(np.uint8)
    return array


# numpy array shape, array type.
# modes that don't need decoding will be available even if opencv
# is not found.
buffer_to_numpy = {
    Core.I420: (lambda w, h: (h + h / 2, w), np.uint8),
    Core.RGB24: (lambda w, h: (h, w, 3), np.uint8),
    Core.BGR24: (lambda w, h: (h, w, 3), np.uint8),
    Core.Y8: (lambda w, h: (h, w), np.uint8),
    Core.Y16: (lambda w, h: (h, w), np.uint16),
    Core.Y32: (lambda w, h: (h, w), np.uint32),
    Core.BAYER_BG16: (lambda w, h: (h, w), np.uint16),
    Core.BAYER_BG8: (lambda w, h: (h, w), np.uint8),
    Core.BAYER_RG16: (lambda w, h: (h, w), np.uint16),
    Core.BAYER_RG8: (lambda w, h: (h, w), np.uint8),
    Core.YUV422PACKED: (lambda w, h: (h, w, 2), np.uint8),
}

post_scale = {Core.BAYER_BG16: 12, Core.BAYER_RG16: 12}


def limaccds_video_buffer_to_img(imgbuf, width, height, mode):

    try:
        shape_fn, dtype = buffer_to_numpy[mode]
    except KeyError:
        raise ValueError("Video mode {0} not supported yet.".format(mode))

    cv_code = opencv_code.get(mode)

    if shape_fn:
        shape = shape_fn(width, height)
    else:
        shape = height, width

    if len(imgbuf) == 0:
        return None

    npbuf = np.ndarray(shape, dtype=dtype, buffer=imgbuf)

    if cv_code is not None:
        npbuf = _decode_video(npbuf, cv_code)

    # TODO : optimize/robustize
    if npbuf.ndim == 3 and npbuf.itemsize > 1:
        npbuf = _scale_to_8bits(npbuf, in_bits=post_scale.get(mode))

    return npbuf

    # code2gray = {
    #     Core.I420: cv2.COLOR_YUV2GRAY_I420,
    #     Core.BGR24: cv2.COLOR_BGR2GRAY,
    #     Core.RGB24: cv2.COLOR_RGB2GRAY,
    #     Core.Y8: None,
    #     Core.Y16: None,
    #     Core.Y32: None
    # }
