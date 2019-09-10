# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Union

from silx.gui import qt
from typing import List
import numpy
from . import scan_model


class Plot(qt.QObject):

    # FIXME: Have to be reworked
    itemAdded = qt.Signal(object)
    itemRemoved = qt.Signal(object)
    structureChanged = qt.Signal()
    styleChanged = qt.Signal()

    def __init__(self, parent=None):
        super(Plot, self).__init__(parent=parent)
        self.__items = []
        self.__styleStrategy = None

    def addItem(self, item: Item):
        self.__items.append(item)
        self.itemAdded.emit(item)
        self.invalidateStructure()

    def removeItem(self, item: Item):
        self.__items.remove(item)
        self.itemRemoved.emit(item)
        self.invalidateStructure()

    def items(self) -> List[Item]:
        # FIXME better to export iterator or read only list
        return self.__items

    def invalidateStructure(self):
        self.structureChanged.emit()
        self.__invalidateStyleStrategy()

    def styleStrategy(self):
        return self.__styleStrategy

    def __invalidateStyleStrategy(self):
        if self.__styleStrategy is None:
            return
        self.__styleStrategy.invalidateStyles()

    def setStyleStrategy(self, styleStrategy: StyleStrategy):
        self.__styleStrategy = styleStrategy
        self.__styleStrategy.setPlot(self)
        self.styleChanged.emit()


class ChannelRef(qt.QObject):

    currentScanDataUpdated = qt.Signal()

    def __init__(self, parent=None, channelName=None, scanName=None):
        super(ChannelRef, self).__init__(parent=parent)
        self.__channelName = channelName

    def _fireCurrentScanDataUpdated(self):
        """"""
        self.currentScanDataUpdated.emit()

    def name(self) -> str:
        return self.__channelName

    def data(self, scan: scan_model.Scan) -> Union[None, numpy.ndarray]:
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        return channel.data()

    def array(self, scan: scan_model.Scan) -> Union[None, numpy.ndarray]:
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        data = channel.data()
        if data is None:
            return None
        return data.array()


class Item(qt.QObject):
    def __init__(self, parent=None):
        super(Item, self).__init__(parent=parent)

    def isValid(self):
        return True

    def getStyle(self):
        plot = self.parent()
        return plot.styleStrategy().getStyleFromItem(self)


_NotComputed = object()
"""Allow to flag an attribute as not computed"""


class AbstractComputableItem(Item):
    """This item use the scan data to process result before displaying it."""

    resultAvailable = qt.Signal(object)

    def __init__(self, parent=None):
        Item.__init__(self, parent=parent)

    def setSource(self, source: Item):
        self.__source = source
        # FIXME: A structural change on the source item have to invalidate the result

    def source(self) -> Item:
        return self.__source

    def isResultComputed(self, scan: scan_model.Scan) -> bool:
        return scan.hasCachedResult(self)

    def reachResult(self, scan: scan_model.Scan):
        # FIXME: implement an asynchronous the cache system
        # FIXME: cache system have to be invalidated when self config changes
        if scan.hasCachedResult(self):
            result = scan.getCachedResult(self)
        else:
            result = self.compute(scan)
            scan.setCachedResult(self, result)
        if not self.isResultValid(result):
            return None
        return result

    def compute(self, scan: scan_model.Scan) -> object:
        raise NotImplementedError()

    def isResultValid(self, result: object) -> bool:
        raise NotImplementedError()


class Style:
    def __init__(self, lineStyle=None, lineColor=None, linePalette=None):
        super(Style, self).__init__()
        self.lineStyle = lineStyle
        self.lineColor = lineColor
        self.linePalette = linePalette


class StyleStrategy:
    def __init__(self):
        self.__cached = {}

    def setPlot(self, plot: Plot):
        self.__plot = plot
        self.invalidateStyles()

    def plot(self) -> Plot:
        return self.__plot

    def invalidateStyles(self):
        pass

    def computeItemStyleFromPlot(self):
        pass

    def getStyleFromItem(self, item: Item) -> Style:
        raise NotImplementedError()
