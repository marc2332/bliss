# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.
"""Contains implementation of concrete objects used to model plots.

It exists 4 kinds of plots: curves, scatter, image, MCAs. Each plot contains
specific items. But it is not a constraint from the architecture.

Here is a list of plot and item inheritance.

.. image:: _static/flint/model/plot_model_item.png
    :alt: Scan model
    :align: center
"""
from __future__ import annotations
from typing import Optional
from typing import NamedTuple

import numpy

from . import scan_model
from . import plot_model
from . import plot_item_model
from ..utils import mathutils


class CurveStatisticMixIn:
    """This item use the scan data to process result before displaying it."""

    def yAxis(self) -> str:
        """Returns the name of the y-axis in which the statistic have to be displayed"""
        source = self.source()
        return source.yAxis()


class DerivativeItem(plot_model.AbstractComputableItem, plot_item_model.CurveMixIn):
    """This item use the scan data to process result before displaying it."""

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(DerivativeItem, self).__getstate__()
        assert "y_axis" not in state
        state["y_axis"] = self.yAxis()
        return state

    def __setstate__(self, state):
        super(DerivativeItem, self).__setstate__(state)
        self.setYAxis(state.pop("y_axis"))

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


class MaxData(NamedTuple):
    max_index: int
    max_location_y: float
    max_location_x: float
    min_y_value: float
    nb_points: int


class MaxCurveItem(plot_model.AbstractIncrementalComputableItem, CurveStatisticMixIn):
    """Implement a statistic which identify the maximum location of a curve."""

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
