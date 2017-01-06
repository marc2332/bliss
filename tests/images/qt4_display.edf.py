#!/usr/bin/env python

import os,time,sys
import EdfFile

os.environ['QUB_SUBPATH'] = 'qt4'

from PyQt4 import QtGui,QtCore

from Qub.CTools import pixmaptools

scaling = pixmaptools.LUT.Scaling()

image = EdfFile.EdfFile('/segfs/bliss/images/edf_test.edf').GetData(0)  # numpy.ndarray

width = image.shape[0]
height = image.shape[1]

qimage = QtGui.QImage(QtCore.QSize(width, height), QtGui.QImage.Format_RGB32)

for ii in range (width):
    for jj in range(height):
        scaled_value = (image[ii][jj]-800)/5
        qimage.setPixel(ii, jj, QtGui.qRgb(scaled_value, scaled_value, scaled_value))

app = QtGui.QApplication(sys.argv)  # main application
label = QtGui.QLabel()


label.setPixmap(QtGui.QPixmap.fromImage(qimage))

label.resize(width, height)
label.show()

app.exec_()

