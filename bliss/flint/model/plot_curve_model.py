# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union
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
        return (state, self.__scansStored, )

    def __setstate__(self, state):
        super(CurvePlot, self).__setstate__(state[0])
        self.__scansStored = state[1]


class ScanItem(plot_model.Item, plot_model.NotStored):
    def __init__(self, parent=None, scan: scan_model.Scan = None):
        super(ScanItem, self).__init__(parent=parent)
        assert(scan is not None)
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
        self.parent().invalidateStructure()
        self.valueChanged.emit(plot_model.ChangeEventType.YAXIS)

    def xData(self, scan: scan_model.Scan) -> Union[None, scan_model.Data]:
        raise NotImplementedError()

    def yData(self, scan: scan_model.Scan) -> Union[None, scan_model.Data]:
        raise NotImplementedError()

    def xArray(self, scan: scan_model.Scan) -> Union[None, numpy.ndarray]:
        data = self.xData(scan)
        if data is None:
            return None
        return data.array()

    def yArray(self, scan: scan_model.Scan) -> Union[None, numpy.ndarray]:
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
        self.__x = None
        self.__y = None
        self.__yAxis = "left"

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

    def xChannel(self) -> plot_model.ChannelRef:
        return self.__x

    def setXChannel(self, channel: plot_model.ChannelRef):
        self.__x = channel
        self.parent().invalidateStructure()

    def yChannel(self) -> plot_model.ChannelRef:
        return self.__y

    def setYChannel(self, channel: plot_model.ChannelRef):
        self.__y = channel
        self.parent().invalidateStructure()

    def yAxis(self) -> str:
        return self.__yAxis

    def setYAxis(self, yAxis: str):
        self.__yAxis = yAxis
        self.parent().invalidateStructure()
        self.valueChanged.emit(plot_model.ChangeEventType.YAXIS)

    def xData(self, scan: scan_model.Scan) -> Union[None, scan_model.Data]:
        channel = self.xChannel()
        if channel is None:
            return None
        data = channel.data(scan)
        if data is None:
            return None
        return data

    def yData(self, scan: scan_model.Scan) -> Union[None, scan_model.Data]:
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
    ) -> Union[None, Tuple[numpy.ndarray, numpy.ndarray]]:
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
            # FIXME: It have to be logged as a result
            print("Error while creating derivative", e)
            return None

        return result

    def xData(self, scan: scan_model.Scan) -> Union[None, scan_model.Data]:
        result = self.reachResult(scan)
        if not self.isResultValid(result):
            return None
        data = result[0]
        return scan_model.Data(self, data)

    def yData(self, scan: scan_model.Scan) -> Union[None, scan_model.Data]:
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

    def compute(self, scan: scan_model.Scan) -> Union[None, MaxData]:
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
