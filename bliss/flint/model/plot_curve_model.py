# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional
from typing import Tuple

import numpy

from . import scan_model
from . import plot_model
from ..utils import mathutils
import collections


class CurvePlot(plot_model.Plot):
    def __init__(self, parent=None):
        super(CurvePlot, self).__init__(parent=parent)
        self.__scansStored = False

    def setScansStored(self, enableStoring: bool):
        self.__scansStored = enableStoring
        self.configurationChanged.emit()

    def isScansStored(self) -> bool:
        return self.__scansStored

    def __getstate__(self):
        state = super(CurvePlot, self).__getstate__()
        return (state, self.__scansStored)

    def __setstate__(self, state):
        super(CurvePlot, self).__setstate__(state[0])
        self.__scansStored = state[1]


class ScanItem(plot_model.Item, plot_model.NotStored):
    def __init__(self, parent=None, scan: scan_model.Scan = None):
        super(ScanItem, self).__init__(parent=parent)
        assert scan is not None
        self.__scan = scan

    def scan(self) -> scan_model.Scan:
        return self.__scan


class CurveMixIn:
    def __init__(self):
        self.__yAxis = "left"

    def yAxis(self) -> str:
        return self.__yAxis

    def setYAxis(self, yAxis: str):
        self.__yAxis = yAxis
        self._emitValueChanged(plot_model.ChangeEventType.YAXIS)

    def xData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        raise NotImplementedError()

    def yData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        raise NotImplementedError()

    def xArray(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        data = self.xData(scan)
        if data is None:
            return None
        return data.array()

    def yArray(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        data = self.yData(scan)
        if data is None:
            return None
        return data.array()


class CurveStatisticMixIn:
    """This item use the scan data to process result before displaying it."""

    def yAxis(self) -> str:
        """Returns the name of the y-axis in which the statistic have to be displayed"""
        source = self.source()
        return source.yAxis()


class CurveItem(plot_model.Item, CurveMixIn):
    def __init__(self, parent: plot_model.Plot = None):
        super(CurveItem, self).__init__(parent=parent)
        self.__x: Optional[plot_model.ChannelRef] = None
        self.__y: Optional[plot_model.ChannelRef] = None
        self.__yAxis: str = "left"

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(CurveItem, self).__getstate__()
        return (state, self.__x, self.__y, self.__yAxis)

    def __setstate__(self, state):
        super(CurveItem, self).__setstate__(state[0])
        self.__x = state[1]
        self.__y = state[2]
        self.__yAxis = state[3]

    def isValid(self):
        return self.__x is not None and self.__y is not None

    def getScanValidation(self, scan: scan_model.Scan) -> Optional[str]:
        """
        Returns None if everything is fine, else a message to explain the problem.
        """
        xx = self.xArray(scan)
        yy = self.yArray(scan)
        if xx is None and yy is None:
            return "No data available for X and Y data"
        elif xx is None:
            return "No data available for X data"
        elif yy is None:
            return "No data available for Y data"
        elif xx.ndim != 1:
            return "Dimension of X data do not match"
        elif yy.ndim != 1:
            return "Dimension of Y data do not match"
        elif len(xx) != len(yy):
            return "Size of X and Y data do not match"
        # It's fine
        return None

    def xChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__x

    def setXChannel(self, channel: Optional[plot_model.ChannelRef]):
        self.__x = channel
        self._emitValueChanged(plot_model.ChangeEventType.X_CHANNEL)

    def yChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__y

    def setYChannel(self, channel: Optional[plot_model.ChannelRef]):
        self.__y = channel
        self._emitValueChanged(plot_model.ChangeEventType.Y_CHANNEL)

    def yAxis(self) -> str:
        return self.__yAxis

    def setYAxis(self, yAxis: str):
        if self.__yAxis == yAxis:
            return
        self.__yAxis = yAxis
        self._emitValueChanged(plot_model.ChangeEventType.YAXIS)

    def xData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        channel = self.xChannel()
        if channel is None:
            return None
        data = channel.data(scan)
        if data is None:
            return None
        return data

    def yData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        channel = self.yChannel()
        if channel is None:
            return None
        data = channel.data(scan)
        if data is None:
            return None
        return data


class DerivativeItem(plot_model.AbstractComputableItem, CurveMixIn):
    """This item use the scan data to process result before displaying it."""

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(DerivativeItem, self).__getstate__()
        return (state, self.yAxis())

    def __setstate__(self, state):
        super(DerivativeItem, self).__setstate__(state[0])
        self.setYAxis(state[1])

    def isResultValid(self, result):
        return result is not None

    def compute(
        self, scan: scan_model.Scan
    ) -> Optional[Tuple[numpy.ndarray, numpy.ndarray]]:
        sourceItem = self.source()

        x = sourceItem.xData(scan)
        y = sourceItem.yData(scan)
        if x is None or y is None:
            return None

        x = x.array()
        y = y.array()
        if x is None or y is None:
            return None

        try:
            result = mathutils.derivate(x, y)
        except Exception as e:
            # FIXME: Maybe it is better to return a special type and then return
            # Managed outside to store it into the validation cache
            scan.setCacheValidation(
                self, self.version(), "Error while creating derivative.\n" + str(e)
            )
            return None

        return result

    def xData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        result = self.reachResult(scan)
        if not self.isResultValid(result):
            return None
        data = result[0]
        return scan_model.Data(self, data)

    def yData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        result = self.reachResult(scan)
        if not self.isResultValid(result):
            return None
        data = result[1]
        return scan_model.Data(self, data)


MaxData = collections.namedtuple(
    "MaxData",
    ["max_index", "max_location_y", "max_location_x", "min_y_value", "nb_points"],
)


class MaxCurveItem(plot_model.AbstractIncrementalComputableItem, CurveStatisticMixIn):
    def isResultValid(self, result):
        return result is not None

    def setSource(self, source: plot_model.Item):
        previousSource = self.source()
        if previousSource is not None:
            previousSource.valueChanged.disconnect(self.__sourceChanged)
        plot_model.AbstractIncrementalComputableItem.setSource(self, source)
        if source is not None:
            source.valueChanged.connect(self.__sourceChanged)
            self.__sourceChanged(plot_model.ChangeEventType.YAXIS)

    def __sourceChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.YAXIS:
            self.valueChanged.emit(plot_model.ChangeEventType.YAXIS)

    def compute(self, scan: scan_model.Scan) -> Optional[MaxData]:
        sourceItem = self.source()

        xx = sourceItem.xArray(scan)
        yy = sourceItem.yArray(scan)
        if xx is None or yy is None:
            return None

        max_index = numpy.argmax(yy)
        min_y_value = numpy.min(yy)
        max_location_x, max_location_y = xx[max_index], yy[max_index]

        result = MaxData(
            max_index, max_location_y, max_location_x, min_y_value, len(xx)
        )
        return result

    def incrementalCompute(
        self, previousResult: MaxData, scan: scan_model.Scan
    ) -> MaxData:
        sourceItem = self.source()

        xx = sourceItem.xArray(scan)
        yy = sourceItem.yArray(scan)
        if xx is None or yy is None:
            raise ValueError("Non empty data is expected")

        nb = previousResult.nb_points
        if nb == len(xx):
            # obviously nothing to compute
            return previousResult

        xx = xx[nb:]
        yy = yy[nb:]

        max_index = numpy.argmax(yy)
        min_y_value = numpy.min(yy)
        max_location_x, max_location_y = xx[max_index], yy[max_index]
        max_index = max_index + nb

        if previousResult.min_y_value < min_y_value:
            min_y_value = previousResult.min_y_value

        if previousResult.max_location_y > max_location_y:
            # Update and return the previous result
            return MaxData(
                previousResult.max_index,
                previousResult.max_location_y,
                previousResult.max_location_x,
                min_y_value,
                nb + len(xx),
            )

        # Update and new return the previous result
        result = MaxData(
            max_index, max_location_y, max_location_x, min_y_value, nb + len(xx)
        )
        return result
