#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.


"""
Python program to test basler camera acquisition in video mode with Lima:
*acquires images and display them in a qt4 widget.
*dumps first image in a file.
"""

import os
import time
import sys

from Lima import Core
from Lima import Basler

os.environ["QUB_SUBPATH"] = "qt4"

from bliss.data.routines.pixmaptools import qt4 as pixmaptools

from PyQt4 import QtGui, QtCore

cam = Basler.Camera("sn://21661817", 8000)  # gc750 id13
# cam = Basler.Camera('sn://21790015', 8000)  # gc3800 id16

# cam.setInterPacketDelay(100)  # units ??

hwint = Basler.Interface(cam)
ct = Core.CtControl(hwint)
video = ct.video()
image = ct.image()
display = ct.display()
display.setNames("basler", "basler")
display.setActive(True)

acq = ct.acquisition()

print("mode=", video.getMode())
video.setGain(0.19)
video.setExposure(0.1)

video.setMode(Core.YUV422PACKED)
# video.setMode(Core.I420)
# video.setMode(Core.Y8)
# video.setMode(Core.BAYER_BG16)
# video.setMode(Core.BAYER_BG8)
video.startLive()

scaling = pixmaptools.LUT.Scaling()

dump_image = True


def refresh():
    global dump_image
    image = video.getLastImage()
    if image.frameNumber() < 0:
        print("not ready...")
        return

    if False:  # scaling.set_custom_mapping(0,255)
        returnFlag, qimage = pixmaptools.LUT.raw_video_2_image(
            image.buffer(),
            image.width(),
            image.height(),
            pixmaptools.LUT.Scaling.Y8,
            scaling,
        )
        if dump_image:
            ff = open("dump_img_as_str_Y8.dat", "a+")
            ff.write(image.buffer())
            ff.close()
            dump_image = False

    if True:
        returnFlag, qimage = pixmaptools.LUT.raw_video_2_image(
            image.buffer(),
            image.width(),
            image.height(),
            pixmaptools.LUT.Scaling.YUV422PACKED,
            scaling,
        )
        if dump_image:
            ff = open("dump_img_as_str_YUV422PACKED.dat", "a+")
            ff.write(image.buffer())
            ff.close()
            dump_image = False

    if False:
        returnFlag, qimage = pixmaptools.LUT.raw_video_2_image(
            image.buffer(),
            image.width(),
            image.height(),
            pixmaptools.LUT.Scaling.BAYER_BG16,
            scaling,
        )
        if dump_image:
            ff = open("dump_img_as_str_BAYER_BG16.dat", "a+")
            ff.write(image.buffer())
            ff.close()
            dump_image = False

    print(video.getLastImageCounter(), image)
    label.setPixmap(QtGui.QPixmap.fromImage(qimage))


app = QtGui.QApplication(sys.argv)  # main application

label = QtGui.QLabel()
label.resize(1800, 1600)
timer = QtCore.QTimer(label)
QtCore.QObject.connect(timer, QtCore.SIGNAL("timeout()"), refresh)
timer.start(100)
label.show()

app.exec_()

timer.stop()
video.stopLive()
