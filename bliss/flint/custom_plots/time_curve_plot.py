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
from silx.gui import icons
from silx.gui.plot import Plot1D
from silx.gui.plot.items import axis as axis_mdl


_logger = logging.getLogger(__name__)


class DurationAction(qt.QAction):

    valueChanged = qt.Signal(float)

    def __init__(self):
        super(DurationAction, self).__init__()
        self.__duration = None
        self.__durations = {}

        self.__menu = qt.QMenu()
        self.__menu.aboutToShow.connect(self.__menuAboutToShow)
        self.setMenu(self.__menu)

    def __menuAboutToShow(self):
        menu = self.sender()
        menu.clear()
        currentDuration = self.__duration
        currentWasFound = False
        group = qt.QActionGroup(menu)
        group.setExclusive(True)
        for value, (label, icon) in self.__durations.items():
            action = qt.QAction()
            action.setText(label)
            action.setData(value)
            action.setIcon(icon)
            action.setCheckable(True)
            if currentDuration == value:
                action.setChecked(True)
                currentWasFound = True
            group.addAction(action)
            menu.addAction(action)
        if currentDuration is not None and not currentWasFound:
            menu.addSeparator()
            action = qt.QAction()
            action.setText(f"{currentDuration}s")
            action.setData(currentDuration)
            action.setCheckable(True)
            action.setChecked(True)
            currentWasFound = True
            group.addAction(action)
            menu.addAction(action)
        group.triggered.connect(self.__actionSelected)

    def __actionSelected(self, action):
        duration = action.data()
        self.setDuration(duration)

    def setDuration(self, duration):
        if self.__duration == duration:
            return
        self.__duration = duration
        self.__updateLookAndFeel()
        self.valueChanged.emit(duration)

    def addDuration(self, label, value, icon):
        if isinstance(icon, str):
            icon = icons.getQIcon(icon)
        self.__durations[value] = label, icon

    def duration(self):
        """Return a duration in second"""
        return self.__duration

    def __updateLookAndFeel(self):
        duration = self.__duration
        label, icon = self.__durations.get(duration, (None, None))
        if icon is None:
            icon = icons.getQIcon("flint:icons/duration-x")
        if label is None:
            label = f"{duration}s"
        self.setToolTip(f"Duration of {label} selected")
        self.setIcon(icon)


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

        self.__duration = 60 * 2

        self.__durationAction = DurationAction()
        self.__durationAction.setCheckable(True)
        self.__durationAction.setChecked(True)
        self.__durationAction.addDuration("1h", 60 * 60, "flint:icons/duration-1h")
        self.__durationAction.addDuration("30m", 30 * 60, "flint:icons/duration-30m")
        self.__durationAction.addDuration("10m", 10 * 60, "flint:icons/duration-10m")
        self.__durationAction.addDuration("5m", 5 * 60, "flint:icons/duration-5m")
        self.__durationAction.addDuration("2m", 2 * 60, "flint:icons/duration-2m")
        self.__durationAction.addDuration("1m", 1 * 60, "flint:icons/duration-1m")
        self.__durationAction.addDuration("30s", 30, "flint:icons/duration-30s")
        self.__durationAction.setDuration(self.__duration)
        self.__durationAction.valueChanged.connect(self.__durationChanged)

        self.__plot.setGraphXLabel("Time")
        xAxis = self.__plot.getXAxis()
        xAxis.setTickMode(axis_mdl.TickMode.TIME_SERIES)
        xAxis.setTimeZone(None)

        self.__plot.setDataMargins(
            xMinMargin=0.0, xMaxMargin=0.0, yMinMargin=0.1, yMaxMargin=0.1
        )

        # FIXME: The toolbar have to be recreated, not updated
        toolbar = self.__plot.toolBar()
        xAutoAction = self.__plot.getXAxisAutoScaleAction()
        toolbar.insertAction(xAutoAction, self.__durationAction)
        xAutoAction.setVisible(False)
        xLogAction = self.__plot.getXAxisLogarithmicAction()
        xLogAction.setVisible(False)

        self.clear()

    def __durationChanged(self, duration):
        self.setXDuration(duration)

    def setXDuration(self, duration):
        self.__durationAction.setDuration(duration)
        self.__duration = duration
        self.__dropOldData()
        self.__safeUpdatePlot()

    def __dropOldData(self):
        xData = self.__data.get(self.__xAxisName)
        if xData is None:
            return
        if len(xData) == 0:
            return
        duration = xData[-1] - xData[0]
        if duration <= self.__duration:
            return

        # FIXME: most of the time only last items with be removed
        # There is maybe no need to recompute the whole array
        distFromLastValueOfView = self.__duration - numpy.abs(
            xData[-1] - self.__duration - xData
        )
        index = numpy.argmax(distFromLastValueOfView)
        if index >= 1:
            index = index - 1
        if index == 0:
            # early skip
            return
        for name, data in self.__data.items():
            data = data[index:]
            self.__data[name] = data

    def getDataRange(self):
        r = self.__plot.getDataRange()
        if r is None:
            return None
        return r[0], r[1]

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

    def addTimeCurveItem(self, yName, **kwargs):
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

    def appendData(self, **kwargs):
        """Update the current data with extra data"""
        for name, data in kwargs.items():
            self.__appendData(name, data)
        self.__dropOldData()
        self.__safeUpdatePlot()

    def resetZoom(self):
        if self.__durationAction.isChecked():
            self.__plot.resetZoom()
            xData = self.__data.get(self.__xAxisName)
            if xData is not None and len(xData) > 0:
                xmax = xData[-1]
                xmin = xmax - self.__duration
                xAxis = self.__plot.getXAxis()
                xAxis.setLimits(xmin, xmax)

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
        self.resetZoom()
