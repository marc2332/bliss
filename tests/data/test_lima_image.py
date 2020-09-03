# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import pytest
import numpy
from bliss.data import lima_image


RAW_IMAGE = b"YATD\x02\x00@\x00\x02\x00\x00\x00\x02\x00\x00\x00\x00\x00\x02\
\x00\x02\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x08\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00o'\x00\x00\xba\x1d\x00\x00\xdc$\x00\
\x00\x89\x1c\x00\x00"

RAW_VIDEO = b"VDEO\x00\x01\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x02\x00\x00\x00\x02\x00\x00\x00 \x00\x00\x00\x00o'\x00\x00\xba\x1d\x00\
\x00\xdc$\x00\x00\x89\x1c\x00\x00"

RAW_YUV422PACKED_VIDEO = (
    b"VDEO\x00\x01\x00\x13\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x02\x00\x00\x00\x04\x00\x00\x00 \x00\x00\x00\x00"
    + b"[L\xffL6\x96\x00\x96\xef\x1dg\x1d\x80\x00\x80\x00"
)

RAW_RGB24_VIDEO = (
    b"VDEO\x00\x01\x00\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x02\x00\x00\x00\x02\x00\x00\x00 \x00\x00\x00\x00"
    + b"\xFF\x00\x00\x00\xFF\x00\x00\x00\xFF\x00\x00\x00"
)

RAW_RGB32_VIDEO = (
    b"VDEO\x00\x01\x00\x07\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x02\x00\x00\x00\x02\x00\x00\x00 \x00\x00\x00\x00"
    + b"\xFF\x00\x00\x00\x00\xFF\x00\x00\x00\x00\xFF\x00\x00\x00\x00\xFF"
)


def test_decode_image_data():
    """Test data from the result of Lima image attr"""
    image = lima_image.decode_devencoded_image(RAW_IMAGE)
    assert image.shape == (2, 2)


def test_decode_image_result():
    """Test the result of Lima image attr"""
    image = lima_image.decode_devencoded_image(("DATA_ARRAY", RAW_IMAGE))
    assert image.shape == (2, 2)


def test_decode_video_data():
    """Test data from the result of Lima video attr"""
    frame = lima_image.decode_devencoded_video(RAW_VIDEO)
    assert frame[0].shape == (2, 2)
    assert frame[1] == 0


def test_decode_video_result():
    """Test result of Lima video attr"""
    frame = lima_image.decode_devencoded_video(("VIDEO_IMAGE", RAW_VIDEO))
    assert frame[0].shape == (2, 2)
    assert frame[1] == 0


def test_decode_data_yuv422packed():
    encoded_image = b"[L\xffL6\x96\x00\x96\xef\x1dg\x1d\x80\x00\x80\x00"
    image = lima_image.decode_rgb_data(
        encoded_image, 2, 4, lima_image.VIDEO_MODES.YUV422PACKED
    )
    assert image.dtype == numpy.uint8
    assert image.shape == (4, 2, 3)
    assert image[0, 0].tolist() == pytest.approx([255, 0, 0], abs=20)
    assert image[1, 0].tolist() == pytest.approx([0, 255, 0], abs=20)
    assert image[2, 0].tolist() == pytest.approx([0, 0, 255], abs=20)
    assert image[3, 0].tolist() == pytest.approx([0, 0, 0], abs=20)


def test_decode_video_yuv422packed():
    frame = lima_image.decode_devencoded_video(("VIDEO_IMAGE", RAW_YUV422PACKED_VIDEO))
    image = frame[0]
    assert image.dtype == numpy.uint8
    assert image.shape == (4, 2, 3)
    assert image[0, 0].tolist() == pytest.approx([255, 0, 0], abs=20)
    assert image[1, 0].tolist() == pytest.approx([0, 255, 0], abs=20)
    assert image[2, 0].tolist() == pytest.approx([0, 0, 255], abs=20)
    assert image[3, 0].tolist() == pytest.approx([0, 0, 0], abs=20)


def test_decode_video_rgb24():
    frame = lima_image.decode_devencoded_video(("VIDEO_IMAGE", RAW_RGB24_VIDEO))
    image = frame[0]
    assert image.dtype == numpy.uint8
    assert image.shape == (2, 2, 3)
    assert image[0, 0].tolist() == pytest.approx([255, 0, 0], abs=20)
    assert image[0, 1].tolist() == pytest.approx([0, 255, 0], abs=20)
    assert image[1, 0].tolist() == pytest.approx([0, 0, 255], abs=20)
    assert image[1, 1].tolist() == pytest.approx([0, 0, 0], abs=20)


def test_decode_video_rgb32():
    frame = lima_image.decode_devencoded_video(("VIDEO_IMAGE", RAW_RGB32_VIDEO))
    image = frame[0]
    assert image.dtype == numpy.uint8
    assert image.shape == (2, 2, 4)
    assert image[0, 0].tolist() == pytest.approx([255, 0, 0, 0], abs=20)
    assert image[0, 1].tolist() == pytest.approx([0, 255, 0, 0], abs=20)
    assert image[1, 0].tolist() == pytest.approx([0, 0, 255, 0], abs=20)
    assert image[1, 1].tolist() == pytest.approx([0, 0, 0, 255], abs=20)
