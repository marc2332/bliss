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

from PyQt4 import QtGui, QtCore

app = QtGui.QApplication(sys.argv)  # main application
label = QtGui.QLabel()

# QImage(const QString & fileName, const char * format = 0)
qimage = QtGui.QImage("lena512color.tiff")
label.setPixmap(QtGui.QPixmap.fromImage(qimage))

label.resize(512, 512)
label.show()

app.exec_()
