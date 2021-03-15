# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations

import logging
import numpy

from silx.gui import qt
from silx.gui.plot import Plot1D

_logger = logging.getLogger(__name__)


class CurveStack(qt.QWidget):
    def __init__(self, parent=None):
        super(CurveStack, self).__init__(parent=parent)
        self.__x = None
        self.__data = None

        self.__plot = Plot1D(self)
        self.__plot.setDataMargins(0.1, 0.1, 0.1, 0.1)

        self.__slider = qt.QSlider(self)
        self.__slider.setObjectName("slider")
        self.__slider.setOrientation(qt.Qt.Horizontal)
        self.__slider.valueChanged.connect(self.__sliderUpdated)

        self.__curveId = qt.QLabel()
        self.__curveId.setAlignment(qt.Qt.AlignCenter)

        layout2 = qt.QHBoxLayout()
        layout2.addWidget(self.__curveId)
        layout2.addWidget(self.__slider)

        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.__plot)
        layout.addLayout(layout2)

        self.clear()

    def getDataRange(self):
        r = self.__plot.getDataRange()
        if r is None:
            return None
        return r[0], r[1]

    def setGraphTitle(self, title: str):
        self.__plot.setGraphTitle(title)

    def setGraphXLabel(self, label: str):
        self.__plot.setGraphXLabel(label)

    def setGraphYLabel(self, label: str):
        self.__plot.setGraphYLabel(label)

    def getPlotWidget(self):
        return self.__plot

    def clear(self):
        self.__x = None
        self.__data = None
        self.__plot.clear()
        self.__slider.setRange(0, 0)
        self.__slider.setEnabled(False)

    def setSelection(self, value: int):
        """Change the curve selection"""
        self.__slider.setValue(value)

    def selection(self) -> int:
        """Returns the selected curve"""
        return self.__slider.value()

    def setData(self, data: numpy.ndarray, x: numpy.ndarray = None, resetZoom=None):
        """
        Set the data of this plot
        
        Arguments:
            data: A 2D data, the first dimension is the curves, the second is
                  the data from the curves.
            x: A 1D data for the projection of the curve in the X axis
        """
        if data is None:
            self.clear()
            return

        assert len(data.shape) == 2
        if x is not None:
            assert len(x) == data.shape[-1]

        nbCurves = data.shape[0]
        self.__data = data
        if x is None:
            self.__x = numpy.arange(nbCurves)
        else:
            self.__x = x

        self.__slider.setRange(0, nbCurves - 1)
        self.__slider.setEnabled(True)
        self.__slider.setValue(0)
        self.__sliderUpdated()
        if resetZoom:
            self.__plot._forceResetZoom()

    def __sliderUpdated(self):
        index = self.__slider.value()
        x = self.__x
        y = self.__data[index]
        self.__curveId.setText(f"{index}")
        self.__plot.clear()
        self.__plot.addCurve(x=x, y=y, legend=f"Curve {index}")
