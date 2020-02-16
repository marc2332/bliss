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
from typing import Dict
from typing import Any

import numpy
import logging

from . import scan_model
from . import plot_model
from . import plot_item_model
from ..utils import mathutils

_logger = logging.getLogger(__name__)


def _getHashableSource(obj: plot_model.Item):
    while isinstance(obj, plot_model.ChildItem):
        obj = obj.source()
    if isinstance(obj, plot_item_model.CurveItem):
        x = obj.xChannel()
        y = obj.yChannel()
        xName = None if x is None else x.name()
        yName = None if y is None else y.name()
        return (xName, yName)
    else:
        _logger.error("Source list not implemented for %s" % type(obj))
        return tuple()


class CurveStatisticItem(plot_model.ChildItem):
    """Statistic displayed on a source item, depending on it y-axis."""

    def inputData(self):
        return _getHashableSource(self.source())

    def yAxis(self) -> str:
        """Returns the name of the y-axis in which the statistic have to be displayed"""
        source = self.source()
        return source.yAxis()

    def setSource(self, source: plot_model.Item):
        previousSource = self.source()
        if previousSource is not None:
            previousSource.valueChanged.disconnect(self.__sourceChanged)
        plot_model.ChildItem.setSource(self, source)
        if source is not None:
            source.valueChanged.connect(self.__sourceChanged)
            self.__sourceChanged(plot_model.ChangeEventType.YAXIS)
            self.__sourceChanged(plot_model.ChangeEventType.X_CHANNEL)
            self.__sourceChanged(plot_model.ChangeEventType.Y_CHANNEL)

    def __sourceChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.YAXIS:
            self._emitValueChanged(plot_model.ChangeEventType.YAXIS)
        if eventType == plot_model.ChangeEventType.Y_CHANNEL:
            self._emitValueChanged(plot_model.ChangeEventType.Y_CHANNEL)
        if eventType == plot_model.ChangeEventType.X_CHANNEL:
            self._emitValueChanged(plot_model.ChangeEventType.X_CHANNEL)


class DerivativeData(NamedTuple):
    xx: numpy.ndarray
    yy: numpy.ndarray
    nb_points: int


class ComputedCurveItem(plot_model.ChildItem, plot_item_model.CurveMixIn):
    def inputData(self):
        return _getHashableSource(self.source())

    def isResultValid(self, result):
        return result is not None

    def xData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        result = self.reachResult(scan)
        if not self.isResultValid(result):
            return None
        data = result.xx
        return scan_model.Data(self, data)

    def yData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        result = self.reachResult(scan)
        if not self.isResultValid(result):
            return None
        data = result.yy
        return scan_model.Data(self, data)

    def setSource(self, source: plot_model.Item):
        previousSource = self.source()
        if previousSource is not None:
            previousSource.valueChanged.disconnect(self.__sourceChanged)
        plot_model.ChildItem.setSource(self, source)
        if source is not None:
            source.valueChanged.connect(self.__sourceChanged)
            self.__sourceChanged(plot_model.ChangeEventType.X_CHANNEL)
            self.__sourceChanged(plot_model.ChangeEventType.Y_CHANNEL)

    def __sourceChanged(self, eventType):
        if eventType == plot_model.ChangeEventType.Y_CHANNEL:
            self._emitValueChanged(plot_model.ChangeEventType.Y_CHANNEL)
        if eventType == plot_model.ChangeEventType.X_CHANNEL:
            self._emitValueChanged(plot_model.ChangeEventType.X_CHANNEL)


class DerivativeItem(ComputedCurveItem, plot_model.IncrementalComputableMixIn):
    """This item use the scan data to process result before displaying it."""

    EXTRA_POINTS = 5
    """Extra points needed before and after a single point to compute a result"""

    def name(self) -> str:
        return "Derivative"

    def __getstate__(self):
        state: Dict[str, Any] = {}
        state.update(plot_model.ChildItem.__getstate__(self))
        state.update(plot_item_model.CurveMixIn.__getstate__(self))
        return state

    def __setstate__(self, state):
        plot_model.ChildItem.__setstate__(self, state)
        plot_item_model.CurveMixIn.__setstate__(self, state)

    def compute(self, scan: scan_model.Scan) -> Optional[DerivativeData]:
        sourceItem = self.source()

        xx = sourceItem.xArray(scan)
        yy = sourceItem.yArray(scan)
        if xx is None or yy is None:
            return None

        try:
            derived = mathutils.derivate(xx, yy)
        except Exception as e:
            _logger.debug("Error while computing derivative", exc_info=True)
            result = DerivativeData(numpy.array([]), numpy.array([]), len(xx))
            raise plot_model.ComputeError(
                "Error while creating derivative.\n" + str(e), result=result
            )

        return DerivativeData(derived[0], derived[1], len(xx))

    def incrementalCompute(
        self, previousResult: DerivativeData, scan: scan_model.Scan
    ) -> DerivativeData:
        """Compute a data using the previous value as basis

        The derivative function expect 5 extra points before and after the
        points it can compute.

        The last computed point have to be recomputed.

        This code is deeply coupled with the implementation of the derivative
        function.
        """
        sourceItem = self.source()
        xx = sourceItem.xArray(scan)
        yy = sourceItem.yArray(scan)
        if xx is None or yy is None:
            raise ValueError("Non empty data expected")

        nb = previousResult.nb_points
        if nb == len(xx):
            # obviously nothing to compute
            return previousResult
        nextNb = len(xx)

        # The last point have to be recomputed
        LAST = 1

        if len(xx) <= 2 * self.EXTRA_POINTS + LAST:
            return DerivativeData(numpy.array([]), numpy.array([]), nextNb)

        if len(previousResult.xx) == 0:
            # If there is no previous point, there is no need to compute it
            LAST = 0

        xx = xx[nb - 2 * self.EXTRA_POINTS - LAST :]
        yy = yy[nb - 2 * self.EXTRA_POINTS - LAST :]

        derived = mathutils.derivate(xx, yy)

        xx = numpy.append(previousResult.xx[:-1], derived[0])
        yy = numpy.append(previousResult.yy[:-1], derived[1])

        result = DerivativeData(xx, yy, nextNb)
        return result

    def displayName(self, axisName, scan: scan_model.Scan) -> str:
        """Helper to reach the axis display name"""
        sourceItem = self.source()
        if axisName == "x":
            return sourceItem.displayName("x", scan)
        elif axisName == "y":
            return "d(%s)" % sourceItem.displayName("y", scan)
        else:
            assert False


class GaussianFitData(NamedTuple):
    xx: numpy.ndarray
    yy: numpy.ndarray
    fit: mathutils.GaussianFitResult


class GaussianFitItem(ComputedCurveItem, plot_model.ComputableMixIn):
    """This item use the scan data to process result before displaying it."""

    def __getstate__(self):
        state: Dict[str, Any] = {}
        state.update(plot_model.ChildItem.__getstate__(self))
        state.update(plot_item_model.CurveMixIn.__getstate__(self))
        return state

    def __setstate__(self, state):
        plot_model.ChildItem.__setstate__(self, state)
        plot_item_model.CurveMixIn.__setstate__(self, state)

    def compute(self, scan: scan_model.Scan) -> Optional[GaussianFitData]:
        sourceItem = self.source()

        xx = sourceItem.xArray(scan)
        yy = sourceItem.yArray(scan)
        if xx is None or yy is None:
            return None

        try:
            fit = mathutils.fit_gaussian(xx, yy)
        except Exception as e:
            _logger.debug("Error while computing gaussian fit", exc_info=True)
            result = GaussianFitData(numpy.array([]), numpy.array([]), None)
            raise plot_model.ComputeError(
                "Error while creating gaussian fit.\n" + str(e), result=result
            )

        yy = fit.transform(xx)
        return GaussianFitData(xx, yy, fit)

    def name(self) -> str:
        return "Gaussian"

    def displayName(self, axisName, scan: scan_model.Scan) -> str:
        """Helper to reach the axis display name"""
        sourceItem = self.source()
        if axisName == "x":
            return sourceItem.displayName("x", scan)
        elif axisName == "y":
            return "gaussian(%s)" % sourceItem.displayName("y", scan)
        else:
            assert False


class MaxData(NamedTuple):
    max_index: int
    max_location_y: float
    max_location_x: float
    min_y_value: float
    nb_points: int


class MaxCurveItem(CurveStatisticItem, plot_model.IncrementalComputableMixIn):
    """Statistic identifying the maximum location of a curve."""

    def name(self) -> str:
        return "Max"

    def isResultValid(self, result):
        return result is not None

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


class MinData(NamedTuple):
    min_index: int
    min_location_y: float
    min_location_x: float
    max_y_value: float
    nb_points: int


class MinCurveItem(CurveStatisticItem, plot_model.IncrementalComputableMixIn):
    """Statistic identifying the minimum location of a curve."""

    def name(self) -> str:
        return "Min"

    def isResultValid(self, result):
        return result is not None

    def compute(self, scan: scan_model.Scan) -> Optional[MinData]:
        sourceItem = self.source()

        xx = sourceItem.xArray(scan)
        yy = sourceItem.yArray(scan)
        if xx is None or yy is None:
            return None

        min_index = numpy.argmin(yy)
        max_y_value = numpy.max(yy)
        min_location_x, min_location_y = xx[min_index], yy[min_index]

        result = MinData(
            min_index, min_location_y, min_location_x, max_y_value, len(xx)
        )
        return result

    def incrementalCompute(
        self, previousResult: MinData, scan: scan_model.Scan
    ) -> MinData:
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

        min_index = numpy.argmin(yy)
        max_y_value = numpy.max(yy)
        min_location_x, min_location_y = xx[min_index], yy[min_index]
        min_index = min_index + nb

        if previousResult.max_y_value < max_y_value:
            max_y_value = previousResult.max_y_value

        if previousResult.min_location_y < min_location_y:
            # Update and return the previous result
            return MinData(
                previousResult.min_index,
                previousResult.min_location_y,
                previousResult.min_location_x,
                max_y_value,
                nb + len(xx),
            )

        # Update and new return the previous result
        result = MinData(
            min_index, min_location_y, min_location_x, max_y_value, nb + len(xx)
        )
        return result
