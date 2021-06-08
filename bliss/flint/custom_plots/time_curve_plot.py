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


class TimeCurvePlot(qt.QWidget):
    """Curve plot which handle data following the time

    - The X is supposed to be the epoch time
    - The data can be appended
    - The user can choose the amount of time to watch
    """

    def __init__(self, parent=None):
        super(TimeCurvePlot, self).__init__(parent=parent)
        self.__data = {}
        self.__description = {}
        self.__xAxisName = "time"
        self.__plot = Plot1D(self)
        layout = qt.QVBoxLayout(self)
        layout.addWidget(self.__plot)

        self.__plot.setGraphXLabel("Time")
        xAxis = self.__plot.getXAxis()
        xAxis.setTickMode(axis_mdl.TickMode.TIME_SERIES)
        xAxis.setTimeZone(None)

        self.__plot.setDataMargins(
            xMinMargin=0.0, xMaxMargin=0.0, yMinMargin=0.1, yMaxMargin=0.1
        )

        self.clear()

    def __cutData(self):
        pass

    def setGraphGrid(self, which):
        self.__plot.setGraphGrid(which)

    def setGraphTitle(self, title: str):
        self.__plot.setGraphTitle(title)

    def setGraphXLabel(self, label: str):
        self.__plot.setGraphXLabel(label)

    def setGraphYLabel(self, label: str, axis="left"):
        self.__plot.setGraphYLabel(label, axis=axis)

    def getPlotWidget(self):
        return self.__plot

    def clear(self):
        self.__data = {}
        self.__plot.clear()

    def __appendData(self, name, newData):
        if name in self.__data:
            data = self.__data[name]
            data = numpy.concatenate((data, newData))
        else:
            data = newData
        self.__data[name] = data

    def selectCurve(self, yName, **kwargs):
        """Update the plot description"""
        self.__description[yName] = kwargs
        self.__safeUpdatePlot()

    def setXName(self, name):
        """Update the name used as X axis"""
        self.__xAxisName = name
        self.__safeUpdatePlot()

    def setData(self, **kwargs):
        self.__data = dict(kwargs)
        self.__safeUpdatePlot()

    def __safeUpdatePlot(self):
        try:
            self.__updatePlot()
        except Exception:
            _logger.critical("Error while updating the plot", exc_info=True)

    def __updatePlot(self):

        self.__plot.clear()
        xData = self.__data.get(self.__xAxisName)
        if xData is None:
            return

        for name, style in self.__description.items():
            yData = self.__data.get(name)
            if yData is None:
                continue
            if "legend" not in style:
                style["legend"] = name
            style["resetzoom"] = False
            self.__plot.addCurve(xData, yData, **style)
        self.__plot.resetZoom()
