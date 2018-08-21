#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
Python program to test Lima Tango device server

*acquires images and display them in a qt4 widget.
*dumps first image in a file.
"""

import os
import time
import sys
import struct
import numpy

os.environ["QUB_SUBPATH"] = "qt4"
from PyQt4 import QtGui, QtCore

from PyTango import DeviceProxy  # better to use PyTango.gevent ?

from bliss.data.routines.pixmaptools import qt4 as pixmaptools

device = DeviceProxy("id13/limaccds/eh3-vlm1")

print "tango device=", device.name()
print "Exposure Time=", device.acq_expo_time
print "camera_model=", device.camera_model
print "camera_pixelsize=", device.camera_pixelsize
print "camera_type=", device.camera_type
print "image_height=", device.image_height
print "image_width=", device.image_width

# print " =", device.
print "last_image_acquired =", device.last_image_acquired
print "video_mode =", device.video_mode
print "video_live =", device.video_live

print "set video_live TRUE"
device.video_live = True

lutMode = pixmaptools.LUT.Scaling.YUV422PACKED
# lutMode = pixmaptools.LUT.Scaling.BAYER_BG16
# lutMode = pixmaptools.LUT.Scaling.BAYER_RG16


def refresh():
    image_data = device.video_last_image
    print "last_image_acquired =", device.video_last_image_counter

    if image_data[0] == "VIDEO_IMAGE":
        header_fmt = ">IHHqiiHHHH"
        header_size = struct.calcsize(header_fmt)
        _, ver, img_mode, frame_number, width, height, _, _, _, _ = struct.unpack(
            header_fmt, image_data[1][:header_size]
        )

        print "ver=%r, img_mode=%r, frame_number=%r, width=%d, height=%d" % (
            ver,
            img_mode,
            frame_number,
            width,
            height,
        )
        raw_buffer = numpy.fromstring(image_data[1][header_size:], numpy.uint16)
    else:
        print "No header"

    scaling = pixmaptools.LUT.Scaling()
    scaling.autoscale_min_max(raw_buffer, width, height, lutMode)
    # scaling.set_custom_mapping(12 , 50)

    returnFlag, qimage = pixmaptools.LUT.raw_video_2_image(
        raw_buffer, width, height, lutMode, scaling
    )

    label.setPixmap(QtGui.QPixmap.fromImage(qimage))


app = QtGui.QApplication(sys.argv)  # main application

label = QtGui.QLabel()
label.resize(800, 600)

timer = QtCore.QTimer(label)
QtCore.QObject.connect(timer, QtCore.SIGNAL("timeout()"), refresh)
timer.start(200)

label.show()

app.exec_()
timer.stop()
