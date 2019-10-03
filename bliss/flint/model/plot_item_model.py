# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Optional

import numpy
from . import plot_model
from . import scan_model


class McaPlot(plot_model.Plot):
    pass


class McaItem(plot_model.Item):
    def __init__(self, parent: plot_model.Plot = None):
        super(McaItem, self).__init__(parent=parent)
        self.__mca: Optional[plot_model.ChannelRef] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(McaItem, self).__getstate__()
        return (state, self.__mca)

    def __setstate__(self, state):
        super(McaItem, self).__setstate__(state[0])
        self.__mca = state[1]

    def isValid(self):
        return self.__mca is not None

    def mcaChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__mca

    def setMcaChannel(self, channel: plot_model.ChannelRef):
        self.__mca = channel
        self._emitValueChanged(plot_model.ChangeEventType.MCA_CHANNEL)


class ImagePlot(plot_model.Plot):
    pass


class ImageItem(plot_model.Item):
    def __init__(self, parent: plot_model.Plot = None):
        super(ImageItem, self).__init__(parent=parent)
        self.__image: Optional[plot_model.ChannelRef] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(ImageItem, self).__getstate__()
        return (state, self.__image)

    def __setstate__(self, state):
        super(ImageItem, self).__setstate__(state[0])
        self.__image = state[1]

    def isValid(self):
        return self.__image is not None

    def imageChannel(self) -> Optional[plot_model.ChannelRef]:
        return self.__image

    def setImageChannel(self, channel: plot_model.ChannelRef):
        self.__image = channel
        self._emitValueChanged(plot_model.ChangeEventType.IMAGE_CHANNEL)


class ScatterPlot(plot_model.Plot):
    pass


class ScatterItem(plot_model.Item):
    def __init__(self, parent: plot_model.Plot = None):
        super(ScatterItem, self).__init__(parent=parent)
        self.__x: Optional[plot_model.ChannelRef] = None
        self.__y: Optional[plot_model.ChannelRef] = None
        self.__value: Optional[plot_model.ChannelRef] = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(ScatterItem, self).__getstate__()
        return (state, self.__x, self.__y, self.__value)

    def __setstate__(self, state):
        super(ScatterItem, self).__setstate__(state[0])
        self.__x = state[1]
        self.__y = state[2]
        self.__value = state[3]

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

    def setXChannel(self, channel: plot_model.ChannelRef):
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

    def setYChannel(self, channel: plot_model.ChannelRef):
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

    def setValueChannel(self, channel: plot_model.ChannelRef):
        self.__value = channel
        self._emitValueChanged(plot_model.ChangeEventType.VALUE_CHANNEL)

    def valueArray(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        channel = self.__value
        if channel is None:
            return None
        array = channel.array(scan)
        return array
