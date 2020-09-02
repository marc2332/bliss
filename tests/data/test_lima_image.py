# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from bliss.data import lima_image


RAW_IMAGE = b"YATD\x02\x00@\x00\x02\x00\x00\x00\x02\x00\x00\x00\x00\x00\x02\
\x00\x02\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x08\
\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x00\x00\x00\x00\x00\x00\x00\x00o'\x00\x00\xba\x1d\x00\x00\xdc$\x00\
\x00\x89\x1c\x00\x00"

RAW_VIDEO = b"VDEO\x00\x01\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\
\x00\x02\x00\x00\x00\x02\x00\x00\x00 \x00\x00\x00\x00o'\x00\x00\xba\x1d\x00\
\x00\xdc$\x00\x00\x89\x1c\x00\x00"


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
