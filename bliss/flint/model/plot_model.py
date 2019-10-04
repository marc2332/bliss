# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

from __future__ import annotations
from typing import Tuple
from typing import List
from typing import Any
from typing import Optional

import numpy
import enum
import contextlib

from silx.gui import qt
from . import scan_model


class ChangeEventType(enum.Enum):
    YAXIS = enum.auto()
    VISIBILITY = enum.auto()
    CUSTOM_STYLE = enum.auto()
    X_CHANNEL = enum.auto()
    Y_CHANNEL = enum.auto()
    MCA_CHANNEL = enum.auto()
    IMAGE_CHANNEL = enum.auto()
    VALUE_CHANNEL = enum.auto()


class Plot(qt.QObject):

    # FIXME: Have to be reworked
    itemAdded = qt.Signal(object)
    itemRemoved = qt.Signal(object)
    structureChanged = qt.Signal()
    styleChanged = qt.Signal()
    configurationChanged = qt.Signal()
    itemValueChanged = qt.Signal(object, object)
    transactionStarted = qt.Signal()
    transactionFinished = qt.Signal()

    def __init__(self, parent=None):
        super(Plot, self).__init__(parent=parent)
        self.__items: List[Item] = []
        self.__styleStrategy: StyleStrategy = None
        self.__inTransaction: int = 0

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        # Well, NotStored is really specific to the long term storage
        items = [i for i in self.__items if not isinstance(i, NotStored)]
        return (items, self.__styleStrategy)

    def __setstate__(self, state):
        self.__items = state[0]
        self.__styleStrategy = state[1]
        if self.__styleStrategy is not None:
            self.__styleStrategy.setPlot(self)

    def isInTransaction(self) -> bool:
        return self.__inTransaction > 0

    @contextlib.contextmanager
    def transaction(self):
        self.__inTransaction += 1
        self.transactionStarted.emit()
        try:
            yield
        finally:
            self.__inTransaction -= 1
            self.transactionFinished.emit()

    def addItem(self, item: Item):
        item._setPlot(self)
        self.__items.append(item)
        self.itemAdded.emit(item)
        self.invalidateStructure()

    def __itemTree(self, item: Item) -> List[Item]:
        items = [item]
        for i in self.__items:
            if i.isChildOf(item):
                items.append(i)
        return items

    def removeItem(self, item: Item):
        items = self.__itemTree(item)
        for i in items:
            item._setPlot(None)
            self.__items.remove(i)
        for i in items:
            self.itemRemoved.emit(i)
        self.invalidateStructure()

    def items(self) -> List[Item]:
        # FIXME better to export iterator or read only list
        return self.__items

    def invalidateStructure(self):
        self.__invalidateStyleStrategy()
        self.structureChanged.emit()

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


class NotStored:
    """Flag object which not have to be stored"""


class ChannelRef(qt.QObject):

    currentScanDataUpdated = qt.Signal()

    def __init__(self, parent=None, channelName=None, scanName=None):
        super(ChannelRef, self).__init__(parent=parent)
        self.__channelName = channelName

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        return (self.__channelName,)

    def __setstate__(self, state):
        self.__channelName = state[0]

    def _fireCurrentScanDataUpdated(self):
        """"""
        self.currentScanDataUpdated.emit()

    def name(self) -> str:
        return self.__channelName

    def data(self, scan: scan_model.Scan) -> Optional[scan_model.Data]:
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        return channel.data()

    def array(self, scan: scan_model.Scan) -> Optional[numpy.ndarray]:
        channel = scan.getChannelByName(self.__channelName)
        if channel is None:
            return None
        data = channel.data()
        if data is None:
            return None
        return data.array()


class Item(qt.QObject):

    valueChanged = qt.Signal(ChangeEventType)

    def __init__(self, parent=None):
        super(Item, self).__init__(parent=parent)
        self.__isVisible: bool = True
        self.__plot: Optional[Plot] = None
        self.__version = 0

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        return (self.parent(), self.__isVisible)

    def __setstate__(self, state):
        self.setParent(state[0])
        self.setVisible(state[1])

    def version(self) -> int:
        return self.__version

    def isValid(self):
        return True

    def getScanValidation(self, scan: scan_model.Scan) -> Optional[str]:
        """
        Returns None if everything is fine, else a message to explain the problem.
        """
        return None

    def isValidInScan(self, scan: scan_model.Scan) -> bool:
        return self.getErrorMessage(scan) is None

    def getErrorMessage(self, scan: scan_model.Scan) -> Optional[str]:
        if not scan.hasCacheValidation(self, self.version()):
            result: Optional[str] = self.getScanValidation(scan)
            scan.setCacheValidation(self, self.version(), result)
        else:
            result = scan.getCacheValidation(self, self.version())
        return result

    def isChildOf(self, parent: Item) -> bool:
        return False

    def _setPlot(self, plot: Optional[Plot]):
        self.__plot = plot

    def plot(self) -> Optional[Plot]:
        return self.__plot

    def _emitValueChanged(self, eventType: ChangeEventType):
        self.__version = (self.__version + 1) % 0x1000000
        plot = self.plot()
        if plot is not None:
            plot.itemValueChanged.emit(self, eventType)
        self.valueChanged.emit(eventType)

    def setVisible(self, isVisible: bool):
        if self.__isVisible == isVisible:
            return
        self.__isVisible = isVisible
        self._emitValueChanged(ChangeEventType.VISIBILITY)

    def isVisible(self) -> bool:
        return self.__isVisible

    def getStyle(self, scan: scan_model.Scan = None) -> Style:
        plot = self.parent()
        strategy = plot.styleStrategy()
        # FIXME: It means the architecture is not nice
        try:
            return strategy.getStyleFromItem(self, scan)
        except:
            return strategy.getStyleFromItem(self, None)


_NotComputed = object()
"""Allow to flag an attribute as not computed"""


class AbstractComputableItem(Item):
    """This item use the scan data to process result before displaying it."""

    resultAvailable = qt.Signal(object)

    def __init__(self, parent=None):
        Item.__init__(self, parent=parent)
        self.__source: Item = None

    def __reduce__(self):
        return (self.__class__, (), self.__getstate__())

    def __getstate__(self):
        state = super(AbstractComputableItem, self).__getstate__()
        return (state, self.__source)

    def __setstate__(self, state):
        super(AbstractComputableItem, self).__setstate__(state[0])
        self.__source = state[1]

    def isChildOf(self, parent: Item) -> bool:
        source = self.source()
        if source is parent:
            return True
        if source.isChildOf(parent):
            return True
        return False

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

    def compute(self, scan: scan_model.Scan) -> Any:
        raise NotImplementedError()

    def isResultValid(self, result: Any) -> bool:
        raise NotImplementedError()


class AbstractIncrementalComputableItem(AbstractComputableItem):
    def incrementalCompute(self, previousResult: Any, scan: scan_model.Scan) -> Any:
        """Compute a data using the previous value as basis"""
        raise NotImplementedError()


class Style:
    def __init__(
        self,
        lineStyle: str = None,
        lineColor: Tuple[int, int, int] = None,
        linePalette: int = None,
        symbolStyle: str = None,
        symbolSize: float = None,
        symbolColor: Tuple[int, int, int] = None,
        colormapLut: str = None,
    ):
        super(Style, self).__init__()
        self.__lineStyle = lineStyle
        self.__lineColor = lineColor
        self.__linePalette = linePalette
        self.__symbolStyle = symbolStyle
        self.__symbolSize = symbolSize
        self.__symbolColor = symbolColor
        self.__colormapLut = colormapLut

    @property
    def lineStyle(self):
        return self.__lineStyle

    @property
    def lineColor(self):
        return self.__lineColor

    @property
    def linePalette(self):
        return self.__linePalette

    @property
    def symbolStyle(self):
        return self.__symbolStyle

    @property
    def symbolSize(self):
        return self.__symbolSize

    @property
    def symbolColor(self):
        return self.__symbolColor

    @property
    def colormapLut(self):
        return self.__colormapLut


class StyleStrategy:
    def __init__(self):
        self.__plot: Plot = None

    def __reduce__(self):
        return (self.__class__, ())

    def setPlot(self, plot: Plot):
        self.__plot = plot
        self.invalidateStyles()

    def plot(self) -> Plot:
        return self.__plot

    def invalidateStyles(self):
        pass

    def computeItemStyleFromPlot(self):
        pass

    def getStyleFromItem(self, item: Item, scan: scan_model.Scan = None) -> Style:
        raise NotImplementedError()
