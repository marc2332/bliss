#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

import os
import time
import sys

os.environ["QUB_SUBPATH"] = "qt4"

from PyQt4 import QtGui, QtCore

from bliss.data.routines.pixmaptools import qt4 as pixmaptools

scaling = pixmaptools.LUT.Scaling()

f = open("/segfs/bliss/images/dump_img_as_str_YUV422PACKED.dat")
image = f.read()

width = 748
height = 576

returnFlag, qimage = pixmaptools.LUT.raw_video_2_image(
    image, width, height, pixmaptools.LUT.Scaling.YUV422PACKED, scaling
)

app = QtGui.QApplication(sys.argv)  # main application
label = QtGui.QLabel()

label.setPixmap(QtGui.QPixmap.fromImage(qimage))

label.resize(width, height)
label.show()

app.exec_()
