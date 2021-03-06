# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2020 Beamline Control Unit, ESRF
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
from typing import Dict
from typing import Any
from typing import List

import numpy

from . import scan_model
from . import plot_model
from . import style_model


class ScalarPlot(plot_model.Plot):
    """"Define that the relative scan contains data which have to be displayed
    with scalar view (ct widget)."""


class CurvePlot(plot_model.Plot):
    """"Define a plot which mostly draw curves."""

    def __init__(self, parent=None):
        super(CurvePlot, self).__init__(parent=parent)
        self.__scansStored = False

    def setScansStored(self, enableStoring: bool):
        self.__scansStored = enableStoring
        self.valueChanged.emit(plot_model.ChangeEventType.SCANS_STORED)

    def isScansStored(self) -> bool:
        return self.__scansStored

    def __getstate__(self):
        state = super(CurvePlot, self).__getstate__()
        assert "scan_stored" not in state
        state["scan_stored"] = self.__scansStored
        return state

    def __setstate__(self, state):
        super(CurvePlot, self).__setstate__(state)
        self.__scansStored = state.pop("scan_stored")


class ScanItem(plot_model.Item, plot_model.NotStored):
    """Define a specific scan which have to be displayed by the plot."""

    def __init__(self, parent=None, scan: scan_model.Scan = None):
        super(ScanItem, self).__init__(parent=parent)
        assert scan is not None
        self.__scan = scan

    def scan(self) -> scan_model.Scan:
        return self.__scan


class CurveMixIn:
    """Define what have to be provide a curve in order to manage curves from a
    scan and computed curves in the same way."""

    def __init__(self):
        self.__yAxis = "left"

    def __getstate__(self):
        state = {}
        state["y_axis"] = self.yAxis()
        return state

    def __setstate__(self, state):
        self.setYAxis(state.pop("y_axis"))

    def yAxis(self) -> str:
        return self.__yAxis

    def setYAxis(self, yAxis: str):
        if self.__yAxis == yAxis:
            return
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

    def displayName(self, axisName, scan: scan_model.Scan) -> str:
        """Helper to reach the axis display name"""
        raise NotImplementedError()


class CurveItem(plot_model.Item, CurveMixIn):
    """Define a curve as part of a plot.

    X and Y values are defined by a `ChannelRef`.
    """

    def __init__(self, parent: plot_model.Plot = None):
        plot_model.Item.__init__(self, parent=parent)
        CurveMixIn.__init__(self)
        self.__x: Optional[plot_model.ChannelRef] = None
        self.__y: Optional[plot_model.ChannelRef] = None

    def __getstate__(self):
        state: Dict[str, Any] = {}
        state.update(plot_model.Item.__getstate__(self))
        state.update(CurveMixIn.__getstate__(self))
        assert "x" not in state
        assert "y" not in state
        state["x"] = self.__x
        state["y"] = self.__y
        return state

    def __setstate__(self, state):
        plot_model.Item.__setstate__(self, state)
        CurveMixIn.__setstate__(self, state)
        self.__x = state.pop("x")
        self.__y = state.pop("y")

    def isValid(self):
        return self.__x is not None and self.__y is not None

    def isAvailableInScan(self, scan: scan_model.Scan) -> bool:
        """Returns true if this item is available in this scan.

        This only imply that the data source is available.
        """
        if not self.isValid():
            return False
        channel = self.xChannel()
        if channel.channel(scan) is None:
            return False
        channel = self.yChannel()
        if channel.channel(scan) is None:
            return False
        return True

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

    def displayName(self, axisName, scan: scan_model.Scan) -> str:
        """Helper to reach the axis display name"""
        if axisName == "x":
            return self.xChannel().displayName(scan)
        elif axisName == "y":
            return self.yChannel().displayName(scan)
        else:
            assert False

    def __str__(self):
        return "<%s x=%s y=%s yaxis=%s />" % (
            type(self).__name__,
            self.__x,
            self.__y,
            self.yAxis(),
        )


class XIndexCurveItem(CurveItem):
    """Define a curve as part of a plot.

    X is fixed as an index and Y value is defined by a `ChannelRef`.
    """

    def isValid(self):
        channel = self.yChannel()
        return channel is not None

    def isAvailableInScan(self, scan: scan_model.Scan) -> bool:
        """Returns true if this item is available in this scan.

        This only imply that the data source is available.
        """
        if not self.isValid():
            return False
        channel = self.yChannel()
        if channel.channel(scan) is None:
            return False
        return True

    def xData(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        yData = self.yData(scan)
        if yData is None:
            return None
        y = yData.array()
        if y is None:
            return None
        array = numpy.arange(len(y))
        return scan_model.Data(array=array)

    def displayName(self, axisName, scan: scan_model.Scan) -> str:
        """Helper to reach the axis display name"""
        if axisName == "x":
            return "index"
        elif axisName == "y":
            return self.yChannel().displayName(scan)
        else:
            assert False

    def __str__(self):
        return "<%s y=%s yaxis=%s />" % (
            type(self).__name__,
            self.yChannel(),
            self.yAxis(),
        )


class McaPlot(plot_model.Plot):
    """Define a plot which is specific for MCAs."""

    def __init__(self, parent=None):
        plot_model.Plot.__init__(self, parent=parent)
        self.__deviceName: Optional[str] = None

    def deviceName(self) -> Optional[str]:
        return self.__deviceName

    def setDeviceName(self, name: str):
        self.__deviceName = name

    def plotTitle(self) -> str:
        return self.__deviceName

    def hasSameTarget(self, other: plot_model.Plot) -> bool:
        if type(self) is not type(other):
            return False
        if self.__deviceName != other.deviceName():
            return False
        return True


class OneDimDataPlot(plot_model.Plot):
    """Define a plot which is specific for one dim data.

    It is not the same as `CurvePlot` as the content of the channels is 1D for
    each steps of the scan.
    """

    def __init__(self, parent=None):
        plot_model.Plot.__init__(self, parent=parent)
        self.__deviceName: Optional[str] = None
        self.__plotTitle = "%s"

    def setPlotTitle(self, title):
        self.__plotTitle = title

    def deviceName(self) -> Optional[str]:
        return self.__deviceName

    def plotTitle(self) -> str:
        return self.__plotTitle

    def setDeviceName(self, name: str):
        self.__deviceName = name

    def hasSameTarget(self, other: plot_model.Plot) -> bool:
        if type(self) is not type(other):
            return False
        if self.__deviceName != other.deviceName():
            return False
        return True


class McaItem(plot_model.Item):
    """Define a MCA as part of a plot.

    The MCA data is defined by a `ChannelRef`.
    """

    def __init__(self, parent: plot_model.Plot = None):
        super(McaItem, self).__init__(parent=parent)
        self.__mca: Optional[plot_model.ChannelRef] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(McaItem, self).__getstate__()
        assert "mca" not in state
        state["mca"] = self.__mca
        return state

    def __setstate__(self, state):
        super(McaItem, self).__setstate__(state)
        self.__mca = state.pop("mca")

    def isValid(self):
        return self.__mca is not None

    def mcaChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__mca

    def setMcaChannel(self, channel: plot_model.ChannelRef):
        self.__mca = channel
        self._emitValueChanged(plot_model.ChangeEventType.MCA_CHANNEL)


class ImagePlot(plot_model.Plot):
    """Define a plot which displays images."""

    def __init__(self, parent=None):
        plot_model.Plot.__init__(self, parent=parent)
        self.__deviceName: Optional[str] = None

    def deviceName(self) -> Optional[str]:
        return self.__deviceName

    def plotTitle(self) -> str:
        return self.__deviceName

    def setDeviceName(self, name: str):
        self.__deviceName = name

    def hasSameTarget(self, other: plot_model.Plot) -> bool:
        if type(self) is not type(other):
            return False
        if self.__deviceName != other.deviceName():
            return False
        return True


class ImageItem(plot_model.Item):
    """Define an image as part of a plot.

    The image is defined by a `ChannelRef`.
    """

    def __init__(self, parent: plot_model.Plot = None):
        super(ImageItem, self).__init__(parent=parent)
        self.__image: Optional[plot_model.ChannelRef] = None
        self.__colormap = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(ImageItem, self).__getstate__()
        assert "image" not in state
        state["image"] = self.__image
        return state

    def __setstate__(self, state):
        super(ImageItem, self).__setstate__(state)
        self.__image = state.pop("image")

    def isValid(self):
        return self.__image is not None

    def imageChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__image

    def setImageChannel(self, channel: plot_model.ChannelRef):
        self.__image = channel
        self._emitValueChanged(plot_model.ChangeEventType.IMAGE_CHANNEL)

    def setCustomStyle(self, style: style_model.Style):
        result = super(ImageItem, self).setCustomStyle(style)
        if self.__colormap is not None:
            # Make sure the cache is updated
            if style.colormapLut is not None:
                self.__colormap.setName(style.colormapLut)
        return result

    def colormap(self):
        return self.__colormap

    def setColormap(self, colormap):
        self.__colormap = colormap


class RoiItem(plot_model.Item):
    """Define a ROI as part of a plot.
    """

    def __init__(self, parent: plot_model.Plot = None):
        super(RoiItem, self).__init__(parent=parent)
        self.__deviceName: Optional[str] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(RoiItem, self).__getstate__()
        assert "deviceName" not in state
        state["deviceName"] = self.__deviceName
        return state

    def __setstate__(self, state):
        super(RoiItem, self).__setstate__(state)
        self.__deviceName = state.pop("deviceName")

    def name(self) -> str:
        """Returns the name displayed for this item"""
        return self.roiName()

    def roiName(self) -> str:
        """Returns the name of the ROI"""
        return self.__deviceName.split(":")[-1]

    def deviceName(self):
        """Returns the device name defining this ROI.

        The device name is the full device name prefixed by the top master name
        """
        return self.__deviceName

    def setDeviceName(self, name: str):
        """Set the device name containing the ROI.

        The device name is the full device name prefixed by the top master name
        """
        self.__deviceName = name

    def roi(self, scan):
        device = scan.getDeviceByName(self.__deviceName)
        return device.metadata().roi


class ScatterPlot(plot_model.Plot):
    """Define a plot which displays scatters."""


class ScatterItem(plot_model.Item):
    """Define a MCA as part of a plot.

    The X, Y, and Value data are each defined by a `ChannelRef`.
    """

    def __init__(self, parent: plot_model.Plot = None):
        super(ScatterItem, self).__init__(parent=parent)
        self.__x: Optional[plot_model.ChannelRef] = None
        self.__y: Optional[plot_model.ChannelRef] = None
        self.__value: Optional[plot_model.ChannelRef] = None
        self.__groupBy: Optional[List[plot_model.ChannelRef]] = None
        self.__colormap = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(ScatterItem, self).__getstate__()
        assert "x" not in state
        assert "y" not in state
        assert "value" not in state
        state["x"] = self.__x
        state["y"] = self.__y
        state["value"] = self.__value
        return state

    def __setstate__(self, state):
        super(ScatterItem, self).__setstate__(state)
        self.__x = state.pop("x")
        self.__y = state.pop("y")
        self.__value = state.pop("value")

    def isValid(self):
        return (
            self.__x is not None and self.__y is not None and self.__value is not None
        )

    def getScanValidation(self, scan: scan_model.Scan) -> Optional[str]:
        """
        Returns None if everything is fine, else a message to explain the problem.
        """
        xx = self.xArray(scan)
        yy = self.yArray(scan)
        value = self.valueArray(scan)

        if xx is None or yy is None or value is None:
            return "No data available for X or Y or Value data"
        elif self.xChannel().name() == self.yChannel().name():
            return "X and Y axis must differ"
        elif xx.ndim != 1:
            return "Dimension of X data do not match"
        elif yy.ndim != 1:
            return "Dimension of Y data do not match"
        elif value.ndim != 1:
            return "Dimension of Value data do not match"
        elif len(xx) != len(yy):
            return "Size of X and Y data do not match"
        elif len(xx) != len(value):
            return "Size of X and Value data do not match"
        # It's fine
        return None

    def xChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__x

    def setXChannel(self, channel: Optional[plot_model.ChannelRef]):
        self.__x = channel
        self._emitValueChanged(plot_model.ChangeEventType.X_CHANNEL)

    def xArray(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        channel = self.__x
        if channel is None:
            return None
        array = channel.array(scan)
        return array

    def yChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__y

    def setYChannel(self, channel: Optional[plot_model.ChannelRef]):
        self.__y = channel
        self._emitValueChanged(plot_model.ChangeEventType.Y_CHANNEL)

    def yArray(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        channel = self.__y
        if channel is None:
            return None
        array = channel.array(scan)
        return array

    def valueChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__value

    def setValueChannel(self, channel: Optional[plot_model.ChannelRef]):
        self.__value = channel
        self._emitValueChanged(plot_model.ChangeEventType.VALUE_CHANNEL)

    def groupByChannels(self) -> Optional[List[plot_model.ChannelRef]]:
        return self.__groupBy

    def setGroupByChannels(self, channels: Optional[List[plot_model.ChannelRef]]):
        self.__groupBy = channels
        self._emitValueChanged(plot_model.ChangeEventType.GROUP_BY_CHANNELS)

    def valueArray(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        channel = self.__value
        if channel is None:
            return None
        array = channel.array(scan)
        return array

    def setCustomStyle(self, style: style_model.Style):
        result = super(ScatterItem, self).setCustomStyle(style)
        if self.__colormap is not None:
            # Make sure the cache is updated
            if style.colormapLut is not None:
                self.__colormap.setName(style.colormapLut)
        return result

    def colormap(self):
        return self.__colormap

    def setColormap(self, colormap):
        self.__colormap = colormap


class AxisPositionMarker(plot_model.Item, plot_model.NotReused):
    """Define a location of a motor in a plot.

    This item is only displayable when the plot uses its motor
    axis as the plot axis
    """

    def __init__(self, parent: plot_model.Plot = None):
        super(AxisPositionMarker, self).__init__(parent=parent)
        self.__motor: Optional[plot_model.ChannelRef] = None
        self.__position: Optional[float] = None
        self.__text: Optional[str] = None

    def isValid(self):
        return (
            self.__motor is not None
            and self.__position is not None
            and self.__text is not None
        )

    def initProperties(
        self, unique_name: str, ref: plot_model.ChannelRef, position: float, text: str
    ):
        """Define object properties just after construction

        This object is not supposed to be mutable. This avoid to define boilerplat and events
        """
        assert self.__motor is None
        self.__unique_name = unique_name
        self.__motor = ref
        self.__position = position
        self.__text = text

    def motorChannel(self) -> Optional[plot_model.ChannelRef]:
        """Returns the channel reference identifying this motor"""
        return self.__motor

    def position(self) -> Optional[float]:
        """Returns the position of the y-axis in which the statistic have to be displayed"""
        return self.__position

    def text(self) -> Optional[str]:
        """Returns the name of the y-axis in which the statistic have to be displayed"""
        return self.__text

    def unique_name(self) -> str:
        """Returns the name of the y-axis in which the statistic have to be displayed"""
        return self.__unique_name


class MotorPositionMarker(AxisPositionMarker):
    """Deprecated object.

    Created for compatibility since bliss 1.3
    """
