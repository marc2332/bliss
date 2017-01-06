#!/usr/bin/env python

import os,time,sys

from PyQt4 import QtGui,QtCore

app = QtGui.QApplication(sys.argv)  # main application
label = QtGui.QLabel()

# QImage(const QString & fileName, const char * format = 0)
qimage = QtGui.QImage("lena512color.tiff")
label.setPixmap(QtGui.QPixmap.fromImage(qimage))

label.resize(512, 512)
label.show()

app.exec_()

